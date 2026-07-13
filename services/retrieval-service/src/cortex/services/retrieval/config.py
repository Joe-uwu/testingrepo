"""retrieval-service configuration."""

from __future__ import annotations

from cortex.platform.config import ServiceSettings

SERVICE_NAME = "retrieval-service"
GROUP = "retrieval-service"


class RetrievalSettings(ServiceSettings):
    http_port: int = 8004

    # Default k-hop radius for evidence gathering.
    evidence_hops: int = 2

    # Vector arm: Qdrant collection name and embedding dimensionality (must match the
    # embedder). In the memory runtime an in-process index is used and the URL is ignored.
    qdrant_collection: str = "cortex_nodes"
    embedding_dim: int = 256
