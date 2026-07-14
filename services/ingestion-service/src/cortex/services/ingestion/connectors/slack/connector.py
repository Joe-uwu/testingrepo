"""Slack connector: pull channel messages over the Web API.

initial_sync walks every accessible public channel via conversations.list, then
conversations.history per channel; incremental_sync passes ``oldest`` (a Slack ts cursor) so
only newer messages return. Slack push delivery is the Events API (a separate webhook), so
stream() is empty here — matching the GitHub connector's poll/webhook split.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from cortex.contracts.enums import Source
from cortex.contracts.payloads import RawEvent
from cortex.platform.logging import get_logger
from cortex.services.ingestion.base import BaseConnector
from cortex.services.ingestion.connectors._common import RestClient
from cortex.services.ingestion.connectors.slack.normalize import normalize_message

log = get_logger("cortex.ingestion.slack")

SLACK_API = "https://slack.com/api"


class SlackError(RuntimeError):
    """Raised when Slack returns ``{"ok": false}``."""


class SlackConnector(BaseConnector):
    def __init__(
        self,
        client: RestClient,
        *,
        channels: Sequence[str] | None = None,
        page_limit: int | None = None,
    ) -> None:
        super().__init__(Source.SLACK.value, rate_per_sec=10.0, capacity=20)
        self._client = client
        self._channels = list(channels) if channels else None
        self._page_limit = page_limit

    def initial_sync(self) -> Sequence[RawEvent]:
        return self._collect(oldest=None)

    def incremental_sync(self, since: str | None) -> Sequence[RawEvent]:
        return self._collect(oldest=since)

    def stream(self) -> Iterator[RawEvent]:
        return iter(())

    # --- internals ---------------------------------------------------------------

    def _collect(self, *, oldest: str | None) -> list[RawEvent]:
        events: list[RawEvent] = []
        for channel in self._list_channels():
            for msg in self._history(channel["id"], oldest=oldest):
                if msg.get("subtype") in {"channel_join", "channel_leave"}:
                    continue
                events.append(normalize_message(channel, msg))
        deduped = [e for e in events if self.dedup(e.external_id)]
        log.info("slack sync", extra={"extra_fields": {"oldest": oldest, "events": len(deduped)}})
        return deduped

    def _list_channels(self) -> list[dict]:
        if self._channels:
            return [{"id": c, "name": c} for c in self._channels]
        out: list[dict] = []
        for ch in self._paginate("/conversations.list", {"types": "public_channel", "limit": 200}, "channels"):
            if ch.get("is_channel") and not ch.get("is_archived"):
                out.append(ch)
        return out

    def _history(self, channel_id: str, *, oldest: str | None) -> list[dict]:
        params: dict = {"channel": channel_id, "limit": 200}
        if oldest:
            params["oldest"] = oldest
        return list(self._paginate("/conversations.history", params, "messages"))

    def _paginate(self, path: str, params: dict, key: str) -> Iterator[dict]:
        query = dict(params)
        count = 0
        while True:
            payload = self._client.get_json(path, params=query)
            if not payload.get("ok", False):
                raise SlackError(payload.get("error", "unknown slack error"))
            for item in payload.get(key, []):
                yield item
                count += 1
                if self._page_limit is not None and count >= self._page_limit:
                    return
            cursor = (payload.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return
            query["cursor"] = cursor
