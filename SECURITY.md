# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
("Report a vulnerability" on the Security tab) rather than opening a public issue. Include
reproduction steps and affected version/commit. We aim to acknowledge within 3 business days.

## Scope and posture

- **Tenant isolation** — every graph and API query is scoped by `org_id`; there is no
  unscoped read path (ADR-0008). The API resolves the tenant from the request; a real
  deployment resolves it from the caller's JWT rather than the demo `X-Org-Id` header.
- **Secrets** — no secret is committed. Connector credentials and the LLM/AudD-style tokens
  live in a git-ignored `.env` (see `.env.example`) or a Kubernetes Secret in production.
  PKCE OAuth client IDs are public by design; billed bearer tokens must stay server-side.
- **Webhooks** — GitHub deliveries are verified with HMAC-SHA256 (`X-Hub-Signature-256`,
  constant-time compare) before anything is published.
- **No third-party audio/DRM** — streaming connectors are metadata/remote-control only.
- **Supply chain** — an SBOM is produced in CI (`make sbom`); dependencies are pinned by
  minimum version and installed from PyPI/official images.
- **Least privilege** — service containers run as a non-root user; production uses managed
  data stores with their own auth, and secrets are injected, not baked into images.

See `docs/threat-model.md` for the STRIDE analysis and mitigations.

## Supported versions

`main` and the latest tagged release receive security fixes.
