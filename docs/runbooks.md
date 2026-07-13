# Runbooks

Operational playbooks for the alerts in `infra/monitoring/prometheus/alerts/cortex.rules.yml`.
Grafana: *Cortex* folder. Prometheus: :9090. Logs are structured JSON with `trace_id`.

## CortexServiceDown — a service is unscrapeable

1. `kubectl -n <ns> get pods` (or `docker compose ps`) — find the crash-looping/pending pod.
2. `kubectl -n <ns> logs deploy/<service> --tail=200` — read the error.
   - Graph-backed service failing on start → it's waiting for Neo4j (`_wait_for_neo4j`). Check
     the neo4j pod is up; the service retries for ~60s then restarts, so a slow Neo4j
     self-heals on the next restart.
   - `ImagePullBackOff` → the image tag isn't in the registry; re-run the release or fix
     `image.tag`.
3. Confirm recovery: `curl <svc>/ready` returns 200 and the pod is Ready.

## CortexHighErrorRate — 5xx ratio > 5%

1. Grafana → *Platform Overview* → "Error ratio by service" to find the offender.
2. Grafana → Explore → Tempo, filter by the service, open a failing trace; or grep logs by
   `trace_id`.
3. Common causes: a downstream store is down (Neo4j/Qdrant), or a bad deploy — check the last
   release and roll back with `helm rollback cortex`.

## CortexHighLatencyP95 — p95 > 1s

1. *Platform Overview* → "Latency — p95 by service".
2. If it's a graph/retrieval service, check Neo4j/Qdrant health and query load.
3. Scale out: `kubectl -n <ns> scale deploy/<service> --replicas=N` (or bump `replicas` in the
   values file and `helm upgrade`).

## CortexKafkaConsumerLag — a group is > 1000 behind

1. *Pipeline & Kafka* → "Kafka consumer lag by group" to find the lagging stage.
2. Check that stage's pod is healthy and not erroring (its consumer thread logs `consume error`
   on broker issues).
3. Scale the consumer (more replicas share the partitions), or check the broker.
4. Persistent lag with errors → messages may be dead-lettering; inspect the `<topic>.dlq`
   topic.

## CortexPipelineStalled — events ingested but none processed

1. Ingestion is publishing (`cortex_events_published_total` rising) but downstream
   `cortex_events_processed_total` is flat.
2. Almost always Kafka: brokers unreachable, or the consumer groups never joined. Check the
   kafka pod and each service's startup logs.
3. Restart the affected stage; consumers rejoin from their committed offsets.

## Rollback

```bash
helm history cortex -n <ns>
helm rollback cortex <REVISION> -n <ns>
```

## Data-store recovery

- **Neo4j** down: graph-service (and ranking/llm/retrieval) go NotReady and retry. Restore the
  Neo4j pod/managed instance; the schema is re-applied idempotently on reconnect
  (`init_schema`).
- **Qdrant** down: retrieval's vector arm is unavailable; the keyword arm still answers. On
  recovery the index is rebuilt from `graph.changes` (and lazily from the graph on first
  query).
