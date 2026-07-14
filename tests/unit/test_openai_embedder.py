"""Tests for the OpenAI-compatible neural embedder (mock transport, no network/key)."""

from __future__ import annotations

import json

import httpx

from cortex.services.retrieval.embeddings import (
    CachedEmbedder,
    OpenAIEmbedder,
    build_embedder,
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_calls_endpoint_and_orders_by_index():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "m"
        assert request.headers["Authorization"] == "Bearer k"
        inputs = body["input"]
        data = [{"index": i, "embedding": [float(len(t))]} for i, t in enumerate(inputs)]
        # Return out of order to prove the client re-sorts by index.
        return httpx.Response(200, json={"data": list(reversed(data))})

    e = OpenAIEmbedder(model="m", api_key="k", dim=1, http=_client(handler))
    assert e.embed(["ab", "abc"]) == [[2.0], [3.0]]
    assert e.embed([]) == []


def test_dim_from_model_map():
    http = _client(lambda r: httpx.Response(200, json={"data": []}))
    assert OpenAIEmbedder(model="text-embedding-3-small", http=http).dim == 1536
    assert OpenAIEmbedder(model="text-embedding-3-large", http=http).dim == 3072
    assert OpenAIEmbedder(model="unknown-model", http=http).dim == 1536  # sensible default


def test_build_embedder_hashing_default():
    e = build_embedder(provider="hashing", dim=32)
    assert isinstance(e, CachedEmbedder)
    assert e.dim == 32
    assert len(e.embed(["billing service"])[0]) == 32
