"""PagerDuty connector configuration and factory (CORTEX_PAGERDUTY_*)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from cortex.platform.logging import get_logger
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.pagerduty.connector import PagerDutyConnector

log = get_logger("cortex.ingestion.pagerduty")

PAGERDUTY_API = "https://api.pagerduty.com"


class PagerDutySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORTEX_PAGERDUTY_", extra="ignore")

    api_token: str = ""  # REST API key
    api_base_url: str = PAGERDUTY_API


def build_pagerduty_connector(settings: PagerDutySettings | None = None) -> PagerDutyConnector | None:
    settings = settings or PagerDutySettings()
    if not settings.api_token:
        return None
    client = RestClient(
        StaticAuth(f"token={settings.api_token}", scheme="Token"),
        base_url=settings.api_base_url, source="pagerduty",
        headers={"Accept": "application/vnd.pagerduty+json;version=2"},
    )
    log.info("pagerduty connector configured")
    return PagerDutyConnector(client)
