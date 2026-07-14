"""Real OpenAI-compatible reasoner: client parsing (mock transport) + graph integration.

The LlmClient is exercised with an httpx.MockTransport (no network/key). The graph tests use a
fake duck-typed llm to prove the Reason node uses the model when present, that Ground still gates
the citations, and that any LLM error degrades to the deterministic template.
"""

from __future__ import annotations

import json

import httpx

from cortex.contracts.enums import EdgeType, NodeLabel
from cortex.graph_sdk.memory import InMemoryGraphRepository
from cortex.services.llm.graph import GraphReasoner, ReasoningConfig
from cortex.services.llm.graph import nodes as N
from cortex.services.llm.graph.state import ReasoningState
from cortex.services.llm.llm_client import LlmClient
from cortex.services.retrieval.service import RetrievalService

ORG = "org_test"


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _evidence():
    repo = InMemoryGraphRepository()
    svc = repo.upsert_node(org_id=ORG, label=NodeLabel.SERVICE, natural_key="svc-billing",
                           source="github", properties={"name": "billing-service"},
                           provenance_event_id="e1")
    inc = repo.upsert_node(org_id=ORG, label=NodeLabel.INCIDENT, natural_key="inc-1",
                           source="pagerduty", properties={"severity": "SEV1"},
                           provenance_event_id="e2")
    owner = repo.upsert_node(org_id=ORG, label=NodeLabel.PERSON, natural_key="dana",
                             source="github", properties={"name": "Dana"}, provenance_event_id="e3")
    repo.upsert_edge(org_id=ORG, type=EdgeType.AFFECTS, from_id=inc.id, to_id=svc.id,
                     confidence=0.9, discovered_by="rule", provenance_event_id="e4")
    repo.upsert_edge(org_id=ORG, type=EdgeType.OWNS, from_id=owner.id, to_id=svc.id,
                     confidence=1.0, discovered_by="rule", provenance_event_id="e5")
    return RetrievalService(repo).gather_evidence(org_id=ORG, node_id=svc.id, hops=2), svc


# --- LlmClient (mock transport) --------------------------------------------------


def test_llm_client_posts_and_parses_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        assert request.headers["Authorization"] == "Bearer sk-x"
        body = json.loads(request.content)
        seen["body"] = body
        assert body["model"] == "gpt-test"
        assert body["response_format"] == {"type": "json_object"}
        assert body["temperature"] == 0
        assert body["messages"][0]["role"] == "system"
        content = json.dumps({
            "summary": "billing-service is at risk",
            "explanation": "An open SEV1 incident affects it.",
            "actions": [{"title": "Hold the deploy", "detail": "wait for the incident to clear"}],
        })
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = LlmClient(model="gpt-test", api_key="sk-x", http=_client(handler))
    result = client.reason(
        anchor_display="billing-service", risk_score=0.9,
        findings=["incident inc-1 affects billing-service"],
        entities=[{"display": "billing-service", "label": "Service"}],
    )
    assert result["summary"] == "billing-service is at risk"
    assert result["explanation"].startswith("An open SEV1")
    assert result["actions"][0]["title"] == "Hold the deploy"
    # The findings/entities are actually handed to the model, not dropped.
    assert "inc-1" in json.dumps(seen["body"]["messages"])


# --- Reason node + full pipeline with a fake model -------------------------------


class _FakeLlm:
    def __init__(self) -> None:
        self.calls = 0

    def reason(self, *, anchor_display, risk_score, findings, entities):
        self.calls += 1
        self.seen = {"anchor": anchor_display, "findings": findings, "entities": entities}
        return {
            "summary": "LLM summary",
            "explanation": "LLM explanation",
            "actions": [{"title": "Do the LLM thing", "detail": "because the model said so"}],
        }


class _RaisingLlm:
    def reason(self, **_):
        raise RuntimeError("api unavailable")


def test_reason_node_uses_llm_when_present():
    ev, _svc = _evidence()
    cfg = ReasoningConfig(llm=_FakeLlm())
    state = N.graph_traverse(ReasoningState(org_id=ORG, node_id=ev.anchor.id, risk_score=0.9,
                                            evidence=ev), cfg)
    state = N.reason(state, cfg)
    assert state.summary == "LLM summary"
    assert state.explanation == "LLM explanation"
    assert state.llm_actions and state.llm_actions[0]["title"] == "Do the LLM thing"
    assert cfg.llm.seen["anchor"] == ev.anchor.display()
    assert cfg.llm.seen["findings"]  # graph findings were passed through


def test_pipeline_uses_llm_output_and_still_grounds():
    ev, svc = _evidence()
    fake = _FakeLlm()
    result = GraphReasoner(ReasoningConfig(llm=fake)).reason(ev, 0.9)
    assert fake.calls == 1
    assert result.node_id == svc.id
    assert result.summary == "LLM summary"
    assert any(a.title == "Do the LLM thing" for a in result.actions)
    # Grounding is independent of the model: citations still resolve to real evidence.
    node_ids = {n.id for n in ev.nodes}
    edge_ids = {e.id for e in ev.edges}
    assert len(result.citations) >= 2
    for c in result.citations:
        assert (c.ref_id in node_ids) if c.kind == "node" else (c.ref_id in edge_ids)
    assert 0.0 < result.confidence <= 1.0


def test_pipeline_falls_back_to_template_on_llm_error():
    ev, _svc = _evidence()
    result = GraphReasoner(ReasoningConfig(llm=_RaisingLlm())).reason(ev, 0.9)
    # Template summary + template-derived actions, grounding intact.
    assert "is at risk" in result.summary
    assert any("Hold the deployment" in a.title for a in result.actions)
    assert result.citations and 0.0 < result.confidence <= 1.0


def test_build_reasoner_selects_template_by_default():
    from types import SimpleNamespace

    from cortex.services.llm.graph import build_reasoner

    reasoner = build_reasoner(SimpleNamespace(evidence_hops=3))
    assert reasoner._config.llm is None
