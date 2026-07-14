"""Notion connector configuration and factory (CORTEX_NOTION_*)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from cortex.platform.logging import get_logger
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.notion.connector import NotionConnector

log = get_logger("cortex.ingestion.notion")

NOTION_API = "https://api.notion.com"
NOTION_VERSION = "2022-06-28"


class NotionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORTEX_NOTION_", extra="ignore")

    token: str = ""  # internal integration secret (secret_...)
    api_base_url: str = NOTION_API
    notion_version: str = NOTION_VERSION


def build_notion_connector(settings: NotionSettings | None = None) -> NotionConnector | None:
    settings = settings or NotionSettings()
    if not settings.token:
        return None
    client = RestClient(
        StaticAuth(settings.token),
        base_url=settings.api_base_url, source="notion",
        headers={"Notion-Version": settings.notion_version, "Content-Type": "application/json"},
    )
    log.info("notion connector configured")
    return NotionConnector(client)
