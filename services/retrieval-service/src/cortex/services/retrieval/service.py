"""Hybrid retrieval and evidence gathering.

gather_evidence(node) returns the k-hop subgraph the reasoning layer cites. search() fuses
a graph keyword arm and a vector (embedding) arm with reciprocal-rank fusion. Nodes are
embedded and stored in a vector index; the index is populated incrementally as the graph
changes (index_nodes) and lazily bootstrapped from the repo on first query (ensure_indexed),
so search works even before any change events have flowed.

Defaults are fully offline: a CachedEmbedder(HashingEmbedder) and an InMemoryVectorIndex.
In production a real embedder and QdrantVectorIndex are injected; the retrieval logic is
identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cortex.graph_sdk.models import Edge, Node
from cortex.graph_sdk.repository import GraphRepository
from cortex.services.retrieval.embeddings import CachedEmbedder, Embedder, HashingEmbedder
from cortex.services.retrieval.vectors import InMemoryVectorIndex, VectorIndex, VectorPoint


@dataclass
class EvidenceSet:
    anchor: Node
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def node_by_id(self, node_id: str) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)


class RetrievalService:
    def __init__(
        self,
        repo: GraphRepository,
        *,
        embedder: Embedder | None = None,
        vector_index: VectorIndex | None = None,
    ) -> None:
        self._repo = repo
        self._embedder: Embedder = embedder or CachedEmbedder(HashingEmbedder())
        self._vectors: VectorIndex = vector_index or InMemoryVectorIndex(dim=self._embedder.dim)
        self._indexed_orgs: set[str] = set()

    # --- indexing ----------------------------------------------------------------

    def index_nodes(self, nodes: list[Node]) -> int:
        """Embed and upsert nodes into the vector index (batch). Returns the count."""
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return 0
        texts = [self._node_text(n) for n in nodes]
        vectors = self._embedder.embed(texts)
        points = [
            VectorPoint(node_id=n.id, org_id=n.org_id, vector=v, label=n.label.value, text=t)
            for n, v, t in zip(nodes, vectors, texts)
        ]
        self._vectors.upsert(points)
        return len(points)

    def ensure_indexed(self, org_id: str) -> None:
        """Bootstrap the vector index for an org from the repo, once."""
        if org_id in self._indexed_orgs:
            return
        self.index_nodes(self._repo.all_nodes(org_id=org_id))
        self._indexed_orgs.add(org_id)

    def index_size(self, org_id: str | None = None) -> int:
        return self._vectors.count(org_id=org_id)

    @staticmethod
    def _node_text(node: Node) -> str:
        parts = [node.display(), node.label.value]
        for key in ("title", "name", "body", "summary"):
            value = node.properties.get(key)
            if value:
                parts.append(str(value))
        return " ".join(parts)

    # --- retrieval ---------------------------------------------------------------

    def gather_evidence(self, *, org_id: str, node_id: str, hops: int = 2) -> EvidenceSet | None:
        anchor = self._repo.get_node(org_id=org_id, node_id=node_id)
        if anchor is None:
            return None
        nodes, edges = self._repo.neighborhood(org_id=org_id, node_id=node_id, hops=hops)
        return EvidenceSet(anchor=anchor, nodes=nodes, edges=edges)

    def search(self, *, org_id: str, query: str, limit: int = 20) -> list[Node]:
        self.ensure_indexed(org_id)
        graph_hits = self._keyword_arm(org_id=org_id, query=query)
        vector_hits = self._vector_arm(org_id=org_id, query=query, limit=max(limit * 2, 20))
        fused = _rrf([[n.id for n in graph_hits], [nid for nid, _ in vector_hits]])
        ordered: list[Node] = []
        for node_id in fused[:limit]:
            node = self._repo.get_node(org_id=org_id, node_id=node_id)
            if node:
                ordered.append(node)
        return ordered

    def _keyword_arm(self, *, org_id: str, query: str) -> list[Node]:
        q = query.lower()
        return [n for n in self._repo.all_nodes(org_id=org_id) if q in self._node_text(n).lower()]

    def _vector_arm(self, *, org_id: str, query: str, limit: int) -> list[tuple[str, float]]:
        query_vector = self._embedder.embed([query])[0]
        return self._vectors.search(org_id=org_id, query_vector=query_vector, limit=limit)


def _rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal-rank fusion across heterogeneous arms (docs/design/hybrid-retrieval.md)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, node_id in enumerate(ranking):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda nid: scores[nid], reverse=True)
