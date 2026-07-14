"""Notion connector tests: cursor pagination, title extraction, incremental cutoff, factory."""

from __future__ import annotations

import httpx

from cortex.contracts.enums import Source
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.notion import (
    NotionConnector,
    NotionSettings,
    build_notion_connector,
)


def _client(handler) -> RestClient:
    return RestClient(StaticAuth("secret_x"), base_url="https://api.notion.com",
                      source="notion", headers={"Notion-Version": "2022-06-28"},
                      http=httpx.Client(transport=httpx.MockTransport(handler)))


def _page(pid: str, edited: str, title: str) -> dict:
    return {
        "object": "page", "id": pid, "url": f"https://notion.so/{pid}",
        "created_time": "2026-01-01T00:00:00.000Z", "last_edited_time": edited,
        "last_edited_by": {"id": "user-1"},
        "parent": {"type": "database_id", "database_id": "db-1"},
        "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
    }


def test_search_paginates_and_extracts_title():
    def handler(request):
        body = request.content.decode()
        if '"start_cursor"' not in body:
            return httpx.Response(200, json={
                "results": [_page("p1", "2026-02-02T00:00:00.000Z", "Runbook")],
                "has_more": True, "next_cursor": "CUR2",
            })
        return httpx.Response(200, json={
            "results": [_page("p2", "2026-02-01T00:00:00.000Z", "Design")],
            "has_more": False, "next_cursor": None,
        })

    conn = NotionConnector(_client(handler))
    events = list(conn.initial_sync())
    assert [e.external_id for e in events] == ["notion:p1", "notion:p2"]
    assert all(e.source == Source.NOTION for e in events)
    assert events[0].title == "Runbook"
    assert events[0].actor == "user-1"
    assert events[0].attributes["parent"] == "database_id:db-1"


def test_incremental_stops_at_cursor():
    def handler(request):
        return httpx.Response(200, json={
            "results": [
                _page("p1", "2026-02-02T00:00:00.000Z", "New"),
                _page("p0", "2026-01-01T00:00:00.000Z", "Old"),
            ],
            "has_more": True, "next_cursor": "CUR2",
        })

    conn = NotionConnector(_client(handler))
    events = list(conn.incremental_sync("2026-01-15T00:00:00.000Z"))
    # Sorted desc; stops when it reaches the older page, so only the newer one returns.
    assert [e.external_id for e in events] == ["notion:p1"]


def test_factory_requires_token():
    assert build_notion_connector(NotionSettings()) is None
    assert isinstance(build_notion_connector(NotionSettings(token="secret_x")), NotionConnector)
