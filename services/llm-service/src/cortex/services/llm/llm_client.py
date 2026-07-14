"""OpenAI-compatible chat client for the reasoning graph.

Given the anchor, the graph-derived findings (edge clauses), and the entity list, it asks a
model to produce a summary, explanation, and recommended actions as strict JSON — constrained
to reason only over the supplied evidence. The graph's Ground node still validates every
citation against the evidence, so the model cannot invent facts that survive to the output.

Works with OpenAI, Azure OpenAI, and local Ollama/vLLM by changing ``base_url`` + ``model``.
The HTTP client is injectable, so tests drive it with a mock transport (no network or key).
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You are an SRE assistant. Reason ONLY over the evidence provided — the anchor entity, "
    "the relationship findings, and the entity list. Do not invent entities or facts. "
    "Respond with a single JSON object with keys: "
    '"summary" (one sentence), "explanation" (2-4 sentences grounded in the findings), and '
    '"actions" (array of up to 3 objects with "title" and "detail"). No prose outside the JSON.'
)


class LlmClient:
    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        http=None,
        timeout: float = 30.0,
        temperature: float = 0.0,
    ) -> None:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("LlmClient requires httpx (the 'openai' extra)") from exc
        self._model = model
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._temperature = temperature
        self._http = http if http is not None else httpx.Client(timeout=timeout)

    def reason(
        self, *, anchor_display: str, risk_score: float,
        findings: list[str], entities: list[dict],
    ) -> dict:
        user = json.dumps({
            "anchor": anchor_display,
            "risk_score": round(risk_score, 3),
            "findings": findings,
            "entities": entities,
        })
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        body = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        }
        resp = self._http.post(f"{self._base}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return {
            "summary": str(parsed.get("summary", "")),
            "explanation": str(parsed.get("explanation", "")),
            "actions": [
                {"title": str(a.get("title", "")), "detail": str(a.get("detail", ""))}
                for a in parsed.get("actions", []) if isinstance(a, dict)
            ],
        }
