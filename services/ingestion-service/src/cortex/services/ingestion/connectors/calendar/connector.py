"""Google Calendar connector: pull events per calendar.

initial_sync lists events with singleEvents=true (recurrences expanded) paged by
``nextPageToken``; incremental_sync passes ``updatedMin`` (the cursor) so only events changed
since the last run return. A full sync-token flow (push channels) is Google's real-time path;
this connector polls, so stream() is empty.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.platform.logging import get_logger
from cortex.services.ingestion.base import BaseConnector
from cortex.services.ingestion.connectors._common import RestClient
from cortex.services.ingestion.connectors.calendar.normalize import normalize_event

log = get_logger("cortex.ingestion.calendar")


class CalendarConnector(BaseConnector):
    def __init__(
        self,
        client: RestClient,
        *,
        calendar_ids: Sequence[str] = ("primary",),
        page_size: int = 250,
        page_limit: int | None = None,
    ) -> None:
        super().__init__(Source.CALENDAR.value, rate_per_sec=10.0, capacity=20)
        self._client = client
        self._calendar_ids = list(calendar_ids) or ["primary"]
        self._page_size = page_size
        self._page_limit = page_limit

    def initial_sync(self) -> Sequence[RawEvent]:
        return self._collect(updated_min=None)

    def incremental_sync(self, since: str | None) -> Sequence[RawEvent]:
        return self._collect(updated_min=since)

    def stream(self) -> Iterator[RawEvent]:
        return iter(())

    # --- internals ---------------------------------------------------------------

    def _collect(self, *, updated_min: str | None) -> list[RawEvent]:
        events: list[RawEvent] = []
        for cal_id in self._calendar_ids:
            events.extend(self._events(cal_id, updated_min=updated_min))
        deduped = [e for e in events if self.dedup(e.external_id)]
        log.info(
            "calendar sync",
            extra={"extra_fields": {"updated_min": updated_min, "events": len(deduped)}},
        )
        return deduped

    def _events(self, calendar_id: str, *, updated_min: str | None) -> list[RawEvent]:
        out: list[RawEvent] = []
        params: dict = {
            "singleEvents": "true", "orderBy": "updated", "maxResults": self._page_size,
        }
        if updated_min:
            params["updatedMin"] = updated_min
        page_token: str | None = None
        while True:
            if page_token:
                params["pageToken"] = page_token
            payload = self._client.get_json(
                f"/calendars/{calendar_id}/events", params=params
            )
            for event in payload.get("items", []):
                out.append(normalize_event(calendar_id, event))
                if self._page_limit is not None and len(out) >= self._page_limit:
                    return out
            page_token = payload.get("nextPageToken")
            if not page_token:
                return out
