"""ingestion-service process entrypoint.

Registers whichever connectors have credentials configured; each source contributes its real
connector when its CORTEX_<SOURCE>_* credentials are present (build_* returns None otherwise).
If nothing is configured the synthetic mock twin is registered so the service is never dead.
Runs the incremental-sync consumer on a background thread and serves the HTTP surface. In a
real deployment a scheduler (Celery beat) drives periodic incremental syncs; here the initial
backfill runs once on start and /api/v1/sync triggers it on demand.
"""

from __future__ import annotations

from cortex.platform.http import Readiness, serve
from cortex.platform.logging import get_logger
from cortex.platform.runtime import build_bus
from cortex.services.ingestion.config import GROUP, SERVICE_NAME, IngestionSettings
from cortex.services.ingestion.connectors import (
    build_calendar_connector,
    build_jira_connector,
    build_notion_connector,
    build_pagerduty_connector,
    build_slack_connector,
)
from cortex.services.ingestion.connectors.github import GitHubSettings, build_github_connector
from cortex.services.ingestion.http import create_app
from cortex.services.ingestion.worker import IngestionWorker

log = get_logger("cortex.ingestion")

# name -> factory. Each returns a connector when its credentials are set, else None.
_CONNECTOR_FACTORIES = {
    "slack": build_slack_connector,
    "jira": build_jira_connector,
    "notion": build_notion_connector,
    "calendar": build_calendar_connector,
    "pagerduty": build_pagerduty_connector,
}


def main() -> None:
    settings = IngestionSettings()
    github_settings = GitHubSettings()
    bus = build_bus(settings, client_id=GROUP)
    worker = IngestionWorker(bus, settings.org_id)

    registered = 0
    github = build_github_connector(github_settings)
    if github is not None:
        worker.register(github)
        registered += 1
        log.info("registered github connector")

    for name, factory in _CONNECTOR_FACTORIES.items():
        connector = factory()
        if connector is not None:
            worker.register(connector)
            registered += 1
            log.info("registered connector", extra={"extra_fields": {"source": name}})

    # Fall back to the synthetic mock twin so the service is never dead without creds.
    if settings.seed_synthetic and registered == 0:
        from cortex.services.ingestion.connectors.mock import MockConnector
        from cortex.tools.synthetic.scenario import deploy_will_fail_scenario

        worker.register(MockConnector("mixed", deploy_will_fail_scenario()))
        log.info("registered synthetic mock connector (no credentials configured)")

    readiness = Readiness()
    app = create_app(worker, webhook_secret=github_settings.webhook_secret, readiness=readiness)

    def _on_ready() -> None:
        if settings.run_initial_sync:
            worker.run_initial_sync()

    serve(
        app, settings, service_name=SERVICE_NAME, bus=bus, group=GROUP,
        readiness=readiness, on_ready=_on_ready,
    )


if __name__ == "__main__":
    main()
