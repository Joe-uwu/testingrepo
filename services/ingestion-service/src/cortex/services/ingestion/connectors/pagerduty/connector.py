"""PagerDuty connector: pull incidents via the REST API.

initial_sync lists incidents paged by ``offset``/``limit`` following the ``more`` flag;
incremental_sync passes ``since`` (the cursor, ISO-8601) so PagerDuty returns only incidents
created/updated in that window. PagerDuty push delivery is a v3 webhook (separate endpoint), so
stream() is empty.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.platform.logging import get_logger
from cortex.services.ingestion.base import BaseConnector
from cortex.services.ingestion.connectors._common import RestClient
from cortex.services.ingestion.connectors.pagerduty.normalize import normalize_incident

log = get_logger("cortex.ingestion.pagerduty")

_STATUSES = ["triggered", "acknowledged", "resolved"]


class PagerDutyConnector(BaseConnector):
    def __init__(
        self,
        client: RestClient,
        *,
        page_size: int = 100,
        page_limit: int | None = None,
    ) -> None:
        super().__init__(Source.PAGERDUTY.value, rate_per_sec=10.0, capacity=20)
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
        offset = 0
        while True:
            params: dict = {
                "limit": self._page_size, "offset": offset,
                "statuses[]": _STATUSES, "sort_by": "created_at:desc",
            }
            if since:
                params["since"] = since
            payload = self._client.get_json("/incidents", params=params)
            incidents = payload.get("incidents", [])
            for inc in incidents:
                events.append(normalize_incident(inc))
                if self._page_limit is not None and len(events) >= self._page_limit:
                    incidents = []
                    break
            offset += len(incidents)
            if not incidents or not payload.get("more") or self._page_limit is not None:
                break
        deduped = [e for e in events if self.dedup(e.external_id)]
        log.info("pagerduty sync", extra={"extra_fields": {"since": since, "events": len(deduped)}})
        return deduped
