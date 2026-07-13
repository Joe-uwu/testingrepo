# Deployment

Three ways to run Cortex, in increasing order of realism: Docker Compose (local), the Helm
chart (Kubernetes), and the release workflow (build + push + deploy).

## Docker Compose (local)

```bash
docker compose -f infra/compose/docker-compose.yml up -d --build   # or: make up
```

Everything on localhost — API :8000, dashboard :3000, Grafana :3001, Prometheus :9090.

## Helm (Kubernetes)

The chart (`deploy/helm/cortex`) deploys the eight services + dashboard, and optionally the
backends (Kafka/Neo4j/Qdrant/Redis) for demo/staging. Images come from
`ghcr.io/<owner>/<service>:<tag>`.

```bash
# render the manifests (no cluster needed) to review them:
helm template cortex deploy/helm/cortex

# install into a cluster (bundled backends, good for a demo):
helm upgrade --install cortex deploy/helm/cortex \
  --namespace cortex --create-namespace --wait

# staging / production overlays:
helm upgrade --install cortex deploy/helm/cortex \
  -f deploy/helm/cortex/values-staging.yaml --set image.tag=staging \
  --namespace cortex-staging --create-namespace --wait
```

Key values (`values.yaml`): `image.registry`/`image.tag`, per-service `replicas`, the shared
`env` block, `infra.enabled` (bundled backends vs managed), and `ingress.*`. Production
(`values-production.yaml`) sets `infra.enabled=false` — point the env vars at your managed
data stores and inject secrets (e.g. `CORTEX_NEO4J_PASSWORD`) via a Kubernetes Secret rather
than the ConfigMap.

Probes: each service has a `startupProbe` on `/health` with a generous window (graph/ranking/
llm wait for Neo4j on boot), then `livenessProbe` on `/health` and `readinessProbe` on
`/ready`, so a pod only receives traffic once it reports ready.

## Release workflow (`.github/workflows/release.yml`)

Push a tag `vX.Y.Z` (or run it manually). It builds and pushes every service + the dashboard
to GHCR tagged with the version, then — **only when you opt in** — deploys.

To enable deploys:

1. Create GitHub Environments `staging` and `production` (add required reviewers on
   `production` for a manual gate).
2. Add repo secrets `KUBE_CONFIG_STAGING` and `KUBE_CONFIG_PRODUCTION` (base64-encoded
   kubeconfig).
3. Set the repo variable `DEPLOY_ENABLED=true`.

Until then the deploy jobs are skipped and the release just publishes images, so tagging a
release stays green without a cluster.

```bash
git tag v0.1.0 && git push origin v0.1.0
```
