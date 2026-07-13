"""VectorIndex contract: the same suite runs against InMemoryVectorIndex and the real
Qdrant adapter.

The ``qdrant`` parameter uses qdrant-client's in-process ``:memory:`` mode (the real Qdrant
query engine, no server) when ``CORTEX_QDRANT_URL`` is unset, and a live Qdrant when it is
(CI provides one). So the adapter is exercised locally and against a server.
"""

from __future__ import annotations

import os
import uuid

import pytest

from cortex.services.retrieval.vectors import InMemoryVectorIndex, VectorIndex, VectorPoint

DIM = 8


def _vec(*first: float) -> list[float]:
    values = list(first)
    return values + [0.0] * (DIM - len(values))


def _qdrant_index() -> VectorIndex:
    pytest.importorskip("qdrant_client")
    from qdrant_client import QdrantClient

    from cortex.services.retrieval.vectors import QdrantVectorIndex

    url = os.environ.get("CORTEX_QDRANT_URL")
    try:
        client = QdrantClient(url=url) if url else QdrantClient(location=":memory:")
        if url:
            client.get_collections()  # force a connection so unreachable -> skip
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"qdrant unavailable: {exc}")
    return QdrantVectorIndex(client=client, collection=f"test_{uuid.uuid4().hex[:8]}", dim=DIM)


@pytest.fixture(params=["memory", "qdrant"])
def index(request) -> VectorIndex:
    if request.param == "memory":
        return InMemoryVectorIndex(dim=DIM)
    return _qdrant_index()


def _seed(index: VectorIndex) -> None:
    index.upsert([
        VectorPoint(node_id="n1", org_id="o1", vector=_vec(1.0, 0.0), label="Service"),
        VectorPoint(node_id="n2", org_id="o1", vector=_vec(0.0, 1.0), label="Incident"),
        VectorPoint(node_id="n3", org_id="o2", vector=_vec(1.0, 0.0), label="Service"),
    ])


def test_nearest_neighbour(index: VectorIndex):
    _seed(index)
    hits = index.search(org_id="o1", query_vector=_vec(1.0, 0.0), limit=5)
    assert hits[0][0] == "n1"
    assert hits[0][1] > hits[-1][1]  # scores ordered


def test_org_isolation(index: VectorIndex):
    _seed(index)
    ids_o1 = {nid for nid, _ in index.search(org_id="o1", query_vector=_vec(1.0, 0.0), limit=10)}
    ids_o2 = {nid for nid, _ in index.search(org_id="o2", query_vector=_vec(1.0, 0.0), limit=10)}
    assert "n3" not in ids_o1
    assert ids_o2 == {"n3"}


def test_label_filter(index: VectorIndex):
    _seed(index)
    hits = index.search(org_id="o1", query_vector=_vec(0.5, 0.5), limit=10, label="Service")
    assert {nid for nid, _ in hits} == {"n1"}


def test_count(index: VectorIndex):
    _seed(index)
    assert index.count() == 3
    assert index.count(org_id="o1") == 2
    assert index.count(org_id="o2") == 1


def test_upsert_is_idempotent(index: VectorIndex):
    _seed(index)
    # Re-upsert n1 with a new vector; count is unchanged and the new vector wins.
    index.upsert([VectorPoint(node_id="n1", org_id="o1", vector=_vec(0.0, 1.0), label="Service")])
    assert index.count(org_id="o1") == 2
    top = index.search(org_id="o1", query_vector=_vec(0.0, 1.0), limit=1)[0][0]
    assert top in {"n1", "n2"}  # both now point along the second axis
