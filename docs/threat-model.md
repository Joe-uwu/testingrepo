# Threat model

Scope: the Cortex platform (eight services, the graph/vector/queue backends, the dashboard,
and the source connectors). STRIDE per trust boundary, with the mitigation that exists today
and the gap where one is deferred.

## Trust boundaries

1. **Internet → connectors / webhooks** — untrusted source events enter here.
2. **Browser → api-service** — the dashboard and API consumers.
3. **Service → service (Kafka)** — internal event bus.
4. **Service → data stores (Neo4j / Qdrant / Redis)** — internal.
5. **CI/CD → registry / cluster** — the release path.

## STRIDE

| Threat | Where | Mitigation | Gap / note |
| --- | --- | --- | --- |
| **Spoofing** | Webhooks (1) | HMAC-SHA256 verification of `X-Hub-Signature-256`, constant-time compare; unsigned deliveries → 401 | — |
| | API callers (2) | Tenant from JWT in production (demo uses `X-Org-Id`) | Wire real JWT auth before exposure |
| **Tampering** | Events on Kafka (3) | Internal network only; envelope is validated against typed payload models on consume | Add TLS + SASL for a shared broker |
| | Graph writes (4) | Only graph-service writes; idempotent MERGE with provenance so a replay can't corrupt state | — |
| **Repudiation** | Any stage | Every node/edge carries `provenance` (asserting event ids); structured logs carry `trace_id` end to end | — |
| **Information disclosure** | Cross-tenant reads (2,4) | Every query is scoped by `org_id`; no unscoped read path exists (ADR-0008) | Enforced in code + `test_org_scoping` |
| | Secrets | No secret committed; `.env` git-ignored, K8s Secret in prod; billed tokens stay server-side (proxy) | — |
| | LLM output | Grounding validator drops any citation not backed by evidence, so reasoning can't leak/invent facts | — |
| **Denial of service** | Connectors (1) | Token-bucket rate limiting + retry/backoff; incremental sync bounded by cursor | Add per-tenant quotas |
| | API (2) | Stateless, horizontally scalable; readiness gating; k8s HPA-ready | Add an ingress rate limit |
| | Reasoning fan-out | Reason threshold bounds how often the LLM stage runs; notification interrupt bar bounds paging | — |
| **Elevation of privilege** | Containers (4) | Non-root user (uid 10001), no build toolchain in runtime image | Add read-only rootfs + drop caps in k8s |
| | CI (5) | Least-privilege `GITHUB_TOKEN` (packages:write); deploy gated on protected Environments + secrets | — |

## Data classification

Source content (PRs, incidents, tickets, messages) is the customer's data; the derived graph
is metadata about it. The Data Safety posture is "collects nothing of its own" — Cortex stores
references and relationships, not third-party audio/DRM content.

## Residual risks (tracked)

- Demo `X-Org-Id` header must be replaced by verified JWT before any real exposure.
- The shared Kafka/Neo4j in compose/staging are unauthenticated (fine for local; managed +
  authenticated stores in production, `infra.enabled=false`).
- The template reasoner is deterministic; a real LLM backend adds prompt-injection surface —
  the grounding validator is the control that still applies to its output.
