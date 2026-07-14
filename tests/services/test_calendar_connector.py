"""Google Calendar connector tests: OAuth refresh, pageToken pagination, normalize, factory."""

from __future__ import annotations

import httpx

from cortex.contracts.enums import Source
from cortex.services.ingestion.connectors._common import RestClient
from cortex.services.ingestion.connectors.calendar import (
    CalendarConnector,
    CalendarSettings,
    GoogleOAuthToken,
    build_calendar_connector,
)


def test_oauth_token_refreshes_and_caches():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert request.url.host == "oauth2.googleapis.com"
        return httpx.Response(200, json={"access_token": "ya29.abc", "expires_in": 3600})

    auth = GoogleOAuthToken(client_id="c", client_secret="s", refresh_token="r",
                            http=httpx.Client(transport=httpx.MockTransport(handler)),
                            clock=lambda: 1000.0)
    assert auth.header() == "Bearer ya29.abc"
    assert auth.header() == "Bearer ya29.abc"  # cached, no second refresh
    assert calls["n"] == 1


def _event(eid: str, updated: str) -> dict:
    return {
        "id": eid, "summary": f"Event {eid}", "description": "desc", "status": "confirmed",
        "updated": updated, "organizer": {"email": "o@x.com"},
        "start": {"dateTime": "2026-03-01T10:00:00Z"}, "end": {"dateTime": "2026-03-01T11:00:00Z"},
        "attendees": [{"email": "a@x.com"}, {"email": "b@x.com"}],
        "htmlLink": "https://cal/e",
    }


def _rest(handler) -> RestClient:
    class _Auth:
        def header(self) -> str:
            return "Bearer ya29.abc"

    return RestClient(_Auth(), base_url="https://www.googleapis.com/calendar/v3",
                      source="calendar", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_events_paginate_and_normalize():
    def handler(request):
        token = dict(request.url.params).get("pageToken")
        if not token:
            return httpx.Response(200, json={"items": [_event("e1", "2026-03-02T00:00:00Z")],
                                             "nextPageToken": "P2"})
        return httpx.Response(200, json={"items": [_event("e2", "2026-03-03T00:00:00Z")]})

    conn = CalendarConnector(_rest(handler), calendar_ids=["primary"])
    events = list(conn.initial_sync())
    assert [e.external_id for e in events] == ["calendar:primary:e1", "calendar:primary:e2"]
    assert all(e.source == Source.CALENDAR for e in events)
    assert events[0].actor == "o@x.com"
    assert events[0].attributes["attendees"] == ["a@x.com", "b@x.com"]
    assert events[0].attributes["start"] == "2026-03-01T10:00:00Z"


def test_incremental_sets_updated_min():
    seen = {}

    def handler(request):
        seen["updatedMin"] = dict(request.url.params).get("updatedMin")
        return httpx.Response(200, json={"items": []})

    conn = CalendarConnector(_rest(handler), calendar_ids=["primary"])
    list(conn.incremental_sync("2026-03-01T00:00:00Z"))
    assert seen["updatedMin"] == "2026-03-01T00:00:00Z"


def test_factory_requires_oauth_creds():
    assert build_calendar_connector(CalendarSettings(client_id="c")) is None
    ok = build_calendar_connector(CalendarSettings(client_id="c", client_secret="s", refresh_token="r"))
    assert isinstance(ok, CalendarConnector)
