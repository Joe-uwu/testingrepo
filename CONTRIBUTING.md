# Contributing

Thanks for helping build Cortex. This repo is a monorepo of independently deployable
services sharing the `cortex.*` namespace (see `CODE_README.md`).

## Development setup

```bash
python -m venv .venv && . .venv/bin/activate     # or your preferred env
pip install -e ".[dev,api,github]"
pre-commit install                                # ruff + format on commit
pytest -q                                         # unit + contract + service + e2e
```

Nothing else is required for the default in-memory runtime. The kafka-runtime and the
infra-backed test suites (Neo4j, Qdrant, Kafka) run against `make up` or in CI.

## Workflow

1. Branch from `main`.
2. Make the change with a test. New behavior needs a test; a bug fix needs a regression test.
3. `ruff check . && ruff format . && mypy && pytest -q` locally (pre-commit runs ruff for you).
4. Open a PR. CI must pass: `test`, `build-and-smoke`, `compose-smoke`, the Neo4j/Qdrant/Kafka
   integration jobs, `dashboard-e2e`, and `helm-lint`.

## Conventions

- **`design.json`-style single source of truth** for cross-cutting concerns — enums, topics,
  and the event envelope live in `packages/contracts` and nowhere else. Changing a wire value
  breaks `tests/contract/test_event_contract.py` on purpose.
- **Ports and adapters.** Services depend on ports (`EventBus`, `GraphRepository`, `Reasoner`,
  `VectorIndex`); the runtime picks the implementation. Add a feature behind its port.
- **Every service is independently deployable** — its own `Dockerfile`, `pyproject.toml`, and
  HTTP surface (`/health`, `/ready`, `/metrics`).
- **Type-checked, linted.** `mypy` strict, `ruff` (line length 100). No `# type: ignore`
  without a reason.
- Record notable decisions as an ADR under `docs/adr/`.

## Commit + PR

- Small, focused commits; imperative subject lines.
- Reference the phase/area in the PR description and note any new env vars or migrations.
