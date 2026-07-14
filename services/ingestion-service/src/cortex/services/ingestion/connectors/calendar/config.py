"""Google Calendar connector configuration and factory (CORTEX_CALENDAR_*)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from cortex.platform.logging import get_logger
from cortex.services.ingestion.connectors._common import RestClient
from cortex.services.ingestion.connectors.calendar.auth import GoogleOAuthToken
from cortex.services.ingestion.connectors.calendar.connector import CalendarConnector

log = get_logger("cortex.ingestion.calendar")

CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class CalendarSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORTEX_CALENDAR_", extra="ignore")

    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    calendar_ids: str = "primary"  # comma-separated calendar IDs
    api_base_url: str = CALENDAR_API

    def calendar_id_list(self) -> list[str]:
        return [c.strip() for c in self.calendar_ids.split(",") if c.strip()] or ["primary"]


def build_calendar_connector(settings: CalendarSettings | None = None) -> CalendarConnector | None:
    settings = settings or CalendarSettings()
    if not (settings.client_id and settings.client_secret and settings.refresh_token):
        return None
    auth = GoogleOAuthToken(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        refresh_token=settings.refresh_token,
    )
    client = RestClient(auth, base_url=settings.api_base_url, source="calendar")
    log.info("calendar connector configured")
    return CalendarConnector(client, calendar_ids=settings.calendar_id_list())
