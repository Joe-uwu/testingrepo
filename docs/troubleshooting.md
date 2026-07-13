# Troubleshooting

Common dev / build / deploy issues and their fixes.

## Local development

**`ModuleNotFoundError: No module named 'cortex'`** — install the workspace editable:
`pip install -e ".[dev,api,github]"`. The `cortex.*` namespace is spread across `packages/` and
`services/` and mapped explicitly in the root `pyproject.toml`; a plain `PYTHONPATH` also works
for tests (see `[tool.pytest.ini_options] pythonpath`).

**Tests skip a lot** — the Neo4j/Qdrant/Kafka suites skip unless `CORTEX_NEO4J_URI` /
`CORTEX_QDRANT_URL` / `CORTEX_KAFKA_BOOTSTRAP` point at a reachable backend. That's expected
offline; CI runs them against service containers.

**`ruff` / `mypy` failures** — run `ruff check . --fix && ruff format .`. Install the hooks
(`pre-commit install`) so this happens on commit.

## Docker Compose

**`manifest unknown` on image pull** — a base image tag was removed upstream (this happened to
`bitnami/kafka`; we use `apache/kafka:3.8.0`). Pin a tag that still exists.

**A service is `Restarting`** — it's likely waiting on a backend. Graph-backed services retry
Neo4j for ~60s then restart; give the stack a minute. `docker compose logs <service>` shows the
`waiting for neo4j` lines. Kafka/qdrant start in seconds.

**Dashboard is blank** — it loads React from a CDN; check the browser can reach `unpkg.com`.
Toggle Demo/Live and confirm the api base URL if using Live mode.

**Ports already in use** — the stack maps 8000–8007, 7474/7687, 9092, 6333, 6379, 9090, 3001,
3000. Stop conflicting processes or change the host ports in compose.

## CI

**`test` job red at collection / `pip install -e .`** — usually a packaging issue in the root
`pyproject.toml` (`package-dir` mapping). Reproduce exactly: `git clone`, `pip install -e .`,
`pytest`.

**`compose-smoke` red** — read the job's "Container status" + per-service logs step; it prints
`docker compose ps -a` and the failing service's logs.

**`dashboard-e2e` red** — a selector didn't match, or the CDN was slow. The Playwright report
lists the failed assertion; run it locally with `cd apps/dashboard/e2e && npx playwright test`.

**`helm-lint` red** — a template error. Reproduce: `helm template cortex deploy/helm/cortex`.

## Kubernetes

**Pods `Pending`** — insufficient resources; lower `replicas`/`resources` in the values file.

**`CrashLoopBackOff` on graph/ranking/llm** — Neo4j isn't reachable at `CORTEX_NEO4J_URI`.
With `infra.enabled=true` the bundled Neo4j takes a minute; with managed stores, verify the
endpoint and credentials (inject the password via a Secret, not the ConfigMap).

**No metrics in Grafana** — check Prometheus → Targets are UP; services carry the
`prometheus.io/scrape` annotations, and the compose Prometheus scrapes them by DNS name.
