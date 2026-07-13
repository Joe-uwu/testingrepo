"""RetrievalService hybrid-search behaviour over the in-memory repo + vector index."""

from __future__ import annotations

from cortex.contracts.enums import NodeLabel
from cortex.graph_sdk.memory import InMemoryGraphRepository
from cortex.services.retrieval.service import RetrievalService

ORG = "o"


def _repo():
    repo = InMemoryGraphRepository()
    billing = repo.upsert_node(
        org_id=ORG, label=NodeLabel.SERVICE, natural_key="svc-billing", source="github",
        properties={"name": "billing-service"}, provenance_event_id="e1",
    )
    incident = repo.upsert_node(
        org_id=ORG, label=NodeLabel.INCIDENT, natural_key="inc-1", source="pagerduty",
        properties={"title": "payments latency spike"}, provenance_event_id="e2",
    )
    return repo, billing, incident


def test_keyword_arm_exact_match():
    repo, billing, _ = _repo()
    svc = RetrievalService(repo)
    ids = [n.id for n in svc.search(org_id=ORG, query="billing", limit=5)]
    assert billing.id in ids


def test_vector_arm_finds_near_miss():
    repo, billing, _ = _repo()
    svc = RetrievalService(repo)
    # "billing services" is not a substring of the node text, so the keyword arm misses it;
    # the vector arm still surfaces the billing service via shared n-grams.
    ids = [n.id for n in svc.search(org_id=ORG, query="billing services", limit=5)]
    assert billing.id in ids


def test_lazy_indexing_populates_vector_index():
    repo, _, _ = _repo()
    svc = RetrievalService(repo)
    assert svc.index_size(ORG) == 0
    svc.search(org_id=ORG, query="anything", limit=1)  # triggers ensure_indexed
    assert svc.index_size(ORG) == 2


def test_incremental_index_nodes():
    repo, _, _ = _repo()
    svc = RetrievalService(repo)
    svc.ensure_indexed(ORG)
    extra = repo.upsert_node(
        org_id=ORG, label=NodeLabel.SERVICE, natural_key="svc-auth", source="github",
        properties={"name": "auth-service"}, provenance_event_id="e3",
    )
    svc.index_nodes([extra])
    ids = [n.id for n in svc.search(org_id=ORG, query="auth", limit=5)]
    assert extra.id in ids
