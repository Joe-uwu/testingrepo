"""retrieval-service configuration."""

from __future__ import annotations

from cortex.platform.config import ServiceSettings

SERVICE_NAME = "retrieval-service"
GROUP = "retrieval-service"


class RetrievalSettings(ServiceSettings):
    http_port: int = 8004

    # Default k-hop radius for evidence gathering.
    evidence_hops: int = 2

    # Vector arm: Qdrant collection name and embedding dimensionality (used by the hashing
    # embedder; the openai embedder derives its dim from the model).
    qdrant_collection: str = "cortex_nodes"
    embedding_dim: int = 256

    # Embedder: "hashing" (offline default) or "openai" (any OpenAI-compatible endpoint —
    # OpenAI, Azure, Ollama, vLLM — set the base URL + model + key).
    embedding_provider: str = "hashing"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
