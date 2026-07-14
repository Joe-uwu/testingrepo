"""Jira connector configuration and factory (CORTEX_JIRA_*)."""

from __future__ import annotations

import base64

from pydantic_settings import BaseSettings, SettingsConfigDict

from cortex.platform.logging import get_logger
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.jira.connector import JiraConnector

log = get_logger("cortex.ingestion.jira")


class JiraSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORTEX_JIRA_", extra="ignore")

    base_url: str = ""     # https://your-site.atlassian.net
    email: str = ""        # Atlassian account email (Basic auth username)
    api_token: str = ""    # Atlassian API token (Basic auth password)
    project: str = ""      # project key to scope the sync; empty = whole site
    jql: str = ""          # explicit JQL overrides project scoping

    def basic_value(self) -> str:
        raw = f"{self.email}:{self.api_token}".encode()
        return base64.b64encode(raw).decode()


def build_jira_connector(settings: JiraSettings | None = None) -> JiraConnector | None:
    settings = settings or JiraSettings()
    if not settings.base_url or not settings.email or not settings.api_token:
        return None
    client = RestClient(
        StaticAuth(settings.basic_value(), scheme="Basic"),
        base_url=settings.base_url, source="jira",
        headers={"Content-Type": "application/json"},
    )
    log.info("jira connector configured", extra={"extra_fields": {"project": settings.project}})
    return JiraConnector(client, project=settings.project or None, jql=settings.jql or None)
