"""retrieval-service process entrypoint.

Consumes graph.changes and embeds + upserts the changed nodes into the vector index
(Qdrant in the kafka runtime, an in-process index otherwise), and serves hybrid retrieval
+ evidence gathering over HTTP to llm-service and api-service.
"""

from __future__ import annotations

from cortex.contracts import Event, Topic
from cortex.contracts.payloads import GraphChanged
from cortex.platform.http import Readiness, serve
from cortex.platform.logging import get_logger
from cortex.platform.observability import METRICS
from cortex.platform.runtime import build_bus, build_graph_repo
from cortex.services.retrieval.config import GROUP, SERVICE_NAME, RetrievalSettings
from cortex.services.retrieval.embeddings import CachedEmbedder, HashingEmbedder
from cortex.services.retrieval.http import create_app
from cortex.services.retrieval.service import RetrievalService
from cortex.services.retrieval.vectors import InMemoryVectorIndex, VectorIndex

log = get_logger("cortex.retrieval")


def _build_vector_index(settings: RetrievalSettings, dim: int) -> VectorIndex:
    if settings.runtime == "kafka":
        from cortex.services.retrieval.vectors import QdrantVectorIndex

        return QdrantVectorIndex(
            url=settings.qdrant_url, collection=settings.qdrant_collection, dim=dim
        )
    return InMemoryVectorIndex(dim=dim)


def main() -> None:
    settings = RetrievalSettings()
    bus = build_bus(settings, client_id=GROUP)
    repo = build_graph_repo(settings)
    embedder = CachedEmbedder(HashingEmbedder(settings.embedding_dim))
    vector_index = _build_vector_index(settings, embedder.dim)
    retrieval = RetrievalService(repo, embedder=embedder, vector_index=vector_index)

    def on_change(event: Event) -> None:
        change = GraphChanged.model_validate(event.payload)
        nodes = [repo.get_node(org_id=event.org_id, node_id=nid) for nid in change.changed_node_ids]
        indexed = retrieval.index_nodes([n for n in nodes if n is not None])
        METRICS.inc("cortex_events_processed_total", service="retrieval-service")
        METRICS.inc("cortex_retrieval_indexed_total", float(indexed), service="retrieval-service")
        log.info("indexed changed nodes", extra={"extra_fields": {"indexed": indexed}})

    bus.subscribe(Topic.GRAPH_CHANGES, on_change, group=GROUP)

    readiness = Readiness()
    app = create_app(retrieval, default_hops=settings.evidence_hops, readiness=readiness)
    serve(app, settings, service_name=SERVICE_NAME, bus=bus, group=GROUP, readiness=readiness)


if __name__ == "__main__":
    main()
