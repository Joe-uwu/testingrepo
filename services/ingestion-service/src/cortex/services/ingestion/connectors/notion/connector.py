"""Notion connector: pull pages and databases via the search endpoint.

Notion has no change feed, so both syncs use POST /v1/search sorted by last_edited_time
(descending) with cursor pagination (``next_cursor`` / ``has_more``). incremental_sync stops
as soon as it reaches an object at or before the cursor timestamp — cheap polling without a
webhook. stream() is empty.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.platform.logging import get_logger
from cortex.services.ingestion.base import BaseConnector
from cortex.services.ingestion.connectors._common import RestClient
from cortex.services.ingestion.connectors.notion.normalize import normalize_object

log = get_logger("cortex.ingestion.notion")


class NotionConnector(BaseConnector):
    def __init__(
        self,
        client: RestClient,
        *,
        page_size: int = 100,
        page_limit: int | None = None,
    ) -> None:
        super().__init__(Source.NOTION.value, rate_per_sec=3.0, capacity=6)  # Notion ~3 req/s
        self._client = client
        self._page_size = page_size
        self._page_limit = page_limit

    def initial_sync(self) -> Sequence[RawEvent]:
        return self._collect(since=None)

    def incremental_sync(self, since: str | None) -> Sequence[RawEvent]:
        return self._collect(since=since)

    def stream(self) -> Iterator[RawEvent]:
        return iter(())

    # --- internals ---------------------------------------------------------------

    def _collect(self, *, since: str | None) -> list[RawEvent]:
        events: list[RawEvent] = []
        cursor: str | None = None
        stop = False
        while not stop:
            body: dict = {
                "page_size": self._page_size,
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            }
            if cursor:
                body["start_cursor"] = cursor
            payload = self._client.post_json("/v1/search", json=body)
            for obj in payload.get("results", []):
                edited = obj.get("last_edited_time")
                if since and edited and str(edited) <= since:
                    stop = True  # sorted desc: everything after is older
                    break
                events.append(normalize_object(obj))
                if self._page_limit is not None and len(events) >= self._page_limit:
                    stop = True
                    break
            if stop or not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
            if not cursor:
                break
        deduped = [e for e in events if self.dedup(e.external_id)]
        log.info("notion sync", extra={"extra_fields": {"since": since, "events": len(deduped)}})
        return deduped
