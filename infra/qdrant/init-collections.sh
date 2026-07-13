#!/usr/bin/env bash
# Create the Cortex vector collection in Qdrant.
#
# retrieval-service also creates this collection on start-up (QdrantVectorIndex), so this
# script is optional — useful for pre-provisioning or manual setup. Collection name and
# vector size must match CORTEX_QDRANT_COLLECTION / CORTEX_EMBEDDING_DIM (default 256).
set -euo pipefail

QDRANT_URL="${CORTEX_QDRANT_URL:-http://localhost:6333}"
COLLECTION="${CORTEX_QDRANT_COLLECTION:-cortex_nodes}"
DIM="${CORTEX_EMBEDDING_DIM:-256}"

echo "creating collection '${COLLECTION}' (dim=${DIM}, cosine) at ${QDRANT_URL}"
curl -fsS -X PUT "${QDRANT_URL}/collections/${COLLECTION}" \
  -H 'Content-Type: application/json' \
  -d "{\"vectors\": {\"size\": ${DIM}, \"distance\": \"Cosine\"}}" \
  && echo

# Payload index on org_id makes the per-tenant filter selective.
curl -fsS -X PUT "${QDRANT_URL}/collections/${COLLECTION}/index" \
  -H 'Content-Type: application/json' \
  -d '{"field_name": "org_id", "field_schema": "keyword"}' \
  && echo

echo "done"
