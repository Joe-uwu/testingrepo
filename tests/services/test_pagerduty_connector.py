"""PagerDuty connector tests: Token auth header, offset pagination, normalize, factory."""

from __future__ import annotations

import httpx

from cortex.contracts.enums import Source
from cortex.services.ingestion.connectors._common import RestClient, StaticAuth
from cortex.services.ingestion.connectors.pagerduty import (
    PagerDutyConnector,
    PagerDutySettings,
    build_pagerduty_connector,
)


def _client(handler) -> RestClient:
    return RestClient(StaticAuth("token=abc", scheme="Token"),
                      base_url="https://api.pagerduty.com", source="pagerduty",
                      headers={"Accept": "application/vnd.pagerduty+json;version=2"},
                      http=httpx.Client(transport=httpx.MockTransport(handler)))


def _incident(iid: str) -> dict:
    return {
        "id": iid, "incident_number": 42, "title": f"Incident {iid}", "status": "triggered",
        "urgency": "high", "created_at": "2026-04-01T00:00:00Z",
        "last_status_change_at": "2026-04-01T01:00:00Z",
        "service": {"summary": "billing-service"},
        "priority": {"summary": "P1"},
        "escalation_policy": {"summary": "primary"},
        "assignments": [{"assignee": {"summary": "Dana"}}],
        "html_url": "https://pd/i",
    }


def test_auth_header_and_pagination():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        offset = int(dict(request.url.params).get("offset", 0))
        if offset == 0:
            return httpx.Response(200, json={"incidents": [_incident("I1")], "more": True})
        return httpx.Response(200, json={"incidents": [_incident("I2")], "more": False})

    conn = PagerDutyConnector(_client(handler), page_size=1)
    events = list(conn.initial_sync())
    assert seen["auth"] == "Token token=abc"
    assert [e.external_id for e in events] == ["pagerduty:I1", "pagerduty:I2"]
    assert all(e.source == Source.PAGERDUTY for e in events)
    e = events[0]
    assert e.title == "Incident I1"
    assert e.actor == "Dana"
    assert e.attributes["urgency"] == "high"
    assert e.attributes["service"] == "billing-service"


def test_incremental_sets_since():
    seen = {}

    def handler(request):
        seen["since"] = dict(request.url.params).get("since")
        return httpx.Response(200, json={"incidents": [], "more": False})

    conn = PagerDutyConnector(_client(handler))
    list(conn.incremental_sync("2026-04-01T00:00:00Z"))
    assert seen["since"] == "2026-04-01T00:00:00Z"


def test_factory_requires_token():
    assert build_pagerduty_connector(PagerDutySettings()) is None
    assert isinstance(build_pagerduty_connector(PagerDutySettings(api_token="k")), PagerDutyConnector)
