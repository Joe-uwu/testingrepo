# retrieval-service

Hybrid retrieval and evidence gathering. Consumes `graph.changes` and embeds + upserts the
changed nodes into a vector index; serves hybrid search and k-hop evidence gathering over
HTTP to llm-service and api-service.

## Topics

- Consumes: `graph.changes` (embeds + indexes changed nodes)

## Retrieval

Two arms fused with reciprocal-rank fusion:

- **Keyword arm** — substring match over each node's text (display + label + key properties).
- **Vector arm** — the query is embedded and matched by cosine similarity against the node
  vectors, so near-misses the keyword arm drops (e.g. "billing services" vs "billing
  service") still surface.

Embeddings come from `HashingEmbedder` (deterministic, offline: character n-gram + word
hashing into a fixed-dim, L2-normalized vector), wrapped in a `CachedEmbedder` (LRU) so
repeated text is not re-embedded. A sentence-transformers/OpenAI embedder drops in behind
the `Embedder` protocol.

The vector index is `InMemoryVectorIndex` in the memory runtime and `QdrantVectorIndex`
(batch upserts, org/label-filtered search) in the kafka runtime. The index is populated
incrementally from `graph.changes` and lazily bootstrapped from the graph on first query.

## HTTP surface

Port `8004` (override with `CORTEX_HTTP_PORT`). `/api` routes are org-scoped via `X-Org-Id`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` `/ready` `/metrics` | Ops |
| POST | `/api/v1/search` | Hybrid keyword + vector search (`{query, limit}`) |
| GET | `/api/v1/evidence/{node_id}?hops=` | k-hop evidence subgraph for a node |
| GET | `/api/v1/index/stats` | Vector count for the org |

## Configuration

`CORTEX_RUNTIME`, `CORTEX_NEO4J_*`, `CORTEX_QDRANT_URL`, `CORTEX_QDRANT_COLLECTION`
(default `cortex_nodes`), `CORTEX_EMBEDDING_DIM` (default `256`, must match the embedder),
`CORTEX_HTTP_PORT` (default `8004`), `CORTEX_EVIDENCE_HOPS` (default `2`),
`CORTEX_OTEL_ENDPOINT`.

## Run

```bash
CORTEX_HTTP_PORT=8004 python -m cortex.services.retrieval.main
docker build -f services/retrieval-service/Dockerfile -t cortex/retrieval-service .
docker run -p 8004:8004 cortex/retrieval-service
```

## Metrics

`cortex_retrieval_queries_total`, `cortex_retrieval_indexed_total`,
`cortex_events_processed_total{service="retrieval-service"}`, plus the shared HTTP metrics.

## Tests

```bash
pytest tests/services/test_retrieval_service.py       # HTTP contract
pytest tests/unit/test_embeddings.py tests/unit/test_hybrid_retrieval.py
pytest tests/contract/test_vector_index.py            # in-memory + Qdrant (:memory: / server)
```
