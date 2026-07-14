"""Shared RestClient tests: retry on 5xx/429, Retry-After, non-retryable 4xx, auth error."""

from __future__ import annotations

import httpx
import pytest

from cortex.services.ingestion.connectors._common import (
    ConnectorAuthError,
    RestClient,
    StaticAuth,
    parse_ts,
)


def _client(handler, **kw) -> RestClient:
    return RestClient(StaticAuth("t"), base_url="https://api.example.com", source="test",
                      http=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def test_retry_on_500_then_success():
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"ok": True})

    c = _client(handler, sleeper=slept.append, base_delay=0.01)
    assert c.get_json("/x") == {"ok": True}
    assert calls["n"] == 3 and len(slept) == 2


def test_retry_after_header_honored():
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={}, headers={"Retry-After": "5"})
        return httpx.Response(200, json={})

    _client(handler, sleeper=slept.append).get_json("/x")
    assert slept == [5.0]


def test_non_retryable_raises():
    c = _client(lambda r: httpx.Response(404, json={"error": "nope"}))
    with pytest.raises(httpx.HTTPStatusError):
        c.get_json("/missing")


def test_static_auth_empty_raises():
    with pytest.raises(ConnectorAuthError):
        StaticAuth("").header()


def test_parse_ts_variants():
    assert parse_ts("2026-01-01T00:00:00Z").year == 2026
    assert parse_ts("1700000000.000100").year == 2023
    assert parse_ts(None) is not None  # falls back to now()
