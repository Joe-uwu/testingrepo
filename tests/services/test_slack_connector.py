"""Slack connector tests: cursor pagination, normalization, incremental, dedup, factory."""

from __future__ import annotations

import httpx
import pytest

from cortex.contracts.enums import Source
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.slack import (
    SlackConnector,
    SlackError,
    SlackSettings,
    build_slack_connector,
)


def _client(handler) -> RestClient:
    return RestClient(StaticAuth("xoxb-t"), base_url="https://slack.com/api",
                      source="slack", http=httpx.Client(transport=httpx.MockTransport(handler)))


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    params = dict(request.url.params)
    if path.endswith("/conversations.list"):
        return httpx.Response(200, json={
            "ok": True,
            "channels": [{"id": "C1", "name": "eng", "is_channel": True, "is_archived": False}],
            "response_metadata": {"next_cursor": ""},
        })
    if path.endswith("/conversations.history"):
        cursor = params.get("cursor")
        if not cursor:
            return httpx.Response(200, json={
                "ok": True,
                "messages": [
                    {"ts": "1700000002.000100", "user": "U1", "text": "deploy failed"},
                    {"ts": "1700000001.000100", "user": "U2", "text": "joined", "subtype": "channel_join"},
                ],
                "response_metadata": {"next_cursor": "PAGE2"},
            })
        return httpx.Response(200, json={
            "ok": True,
            "messages": [{"ts": "1700000000.000100", "user": "U3", "text": "older"}],
            "response_metadata": {"next_cursor": ""},
        })
    return httpx.Response(404, json={"ok": False, "error": "unknown_path"})


def test_initial_sync_paginates_and_normalizes():
    conn = SlackConnector(_client(_handler))
    events = list(conn.initial_sync())
    # channel_join subtype is filtered; two real messages across two history pages.
    assert [e.kind for e in events] == ["message", "message"]
    assert all(e.source == Source.SLACK for e in events)
    first = events[0]
    assert first.external_id == "slack:C1:1700000002.000100"
    assert first.actor == "U1"
    assert first.title == "deploy failed"
    assert first.attributes["channel"] == "eng"


def test_dedup_within_process():
    conn = SlackConnector(_client(_handler))
    assert len(list(conn.initial_sync())) == 2
    assert list(conn.initial_sync()) == []


def test_slack_error_raises():
    def handler(request):
        return httpx.Response(200, json={"ok": False, "error": "invalid_auth"})

    conn = SlackConnector(_client(handler), channels=["C1"])
    with pytest.raises(SlackError):
        list(conn.initial_sync())


def test_incremental_passes_oldest():
    seen = {}

    def handler(request):
        path = request.url.path
        if path.endswith("/conversations.history"):
            seen["oldest"] = dict(request.url.params).get("oldest")
            return httpx.Response(200, json={"ok": True, "messages": [], "response_metadata": {}})
        return _handler(request)

    conn = SlackConnector(_client(handler), channels=["C1"])
    list(conn.incremental_sync("1700000001.000000"))
    assert seen["oldest"] == "1700000001.000000"


def test_factory_requires_token():
    assert build_slack_connector(SlackSettings()) is None
    assert isinstance(build_slack_connector(SlackSettings(bot_token="xoxb-x")), SlackConnector)
