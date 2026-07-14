"""Slack connector configuration and factory (CORTEX_SLACK_*)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from cortex.platform.logging import get_logger
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.slack.connector import SLACK_API, SlackConnector

log = get_logger("cortex.ingestion.slack")


class SlackSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORTEX_SLACK_", extra="ignore")

    bot_token: str = ""  # xoxb-...
    channels: str = ""   # comma-separated channel IDs; empty = every public channel
    api_base_url: str = SLACK_API

    def channel_list(self) -> list[str]:
        return [c.strip() for c in self.channels.split(",") if c.strip()]


def build_slack_connector(settings: SlackSettings | None = None) -> SlackConnector | None:
    settings = settings or SlackSettings()
    if not settings.bot_token:
        return None
    client = RestClient(
        StaticAuth(settings.bot_token), base_url=settings.api_base_url, source="slack"
    )
    log.info("slack connector configured")
    return SlackConnector(client, channels=settings.channel_list() or None)
