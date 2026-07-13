"""Unit tests for the offline embedder and its cache."""

from __future__ import annotations

import math

from cortex.services.retrieval.embeddings import CachedEmbedder, HashingEmbedder


def test_deterministic_and_dimensioned():
    e = HashingEmbedder(dim=128)
    v1 = e.embed(["deploy billing service"])[0]
    v2 = e.embed(["deploy billing service"])[0]
    assert v1 == v2  # stable across calls (and processes: blake2 hashing)
    assert len(v1) == 128


def test_l2_normalized():
    e = HashingEmbedder(dim=64)
    v = e.embed(["incident on payments"])[0]
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-9


def test_similar_text_closer_than_unrelated():
    e = HashingEmbedder(dim=256)
    base, similar, unrelated = e.embed([
        "billing service deployment",
        "billing service deploy",
        "quarterly marketing calendar",
    ])

    def cos(a, b):
        return sum(x * y for x, y in zip(a, b))

    assert cos(base, similar) > cos(base, unrelated)


def test_empty_text_is_zero_vector():
    e = HashingEmbedder(dim=32)
    v = e.embed([""])[0]
    assert v == [0.0] * 32


def test_cache_hits_and_misses():
    inner = HashingEmbedder(dim=32)
    cached = CachedEmbedder(inner, maxsize=8)
    cached.embed(["a", "b"])
    assert cached.misses == 2 and cached.hits == 0
    out = cached.embed(["a", "c"])
    assert cached.hits == 1 and cached.misses == 3
    assert len(out) == 2
    # cached vector matches the underlying embedder
    assert cached.embed(["a"])[0] == inner.embed(["a"])[0]


def test_cache_evicts_lru():
    cached = CachedEmbedder(HashingEmbedder(dim=16), maxsize=2)
    cached.embed(["x"])
    cached.embed(["y"])
    cached.embed(["z"])  # evicts "x"
    before = cached.misses
    cached.embed(["x"])  # miss again (evicted)
    assert cached.misses == before + 1
