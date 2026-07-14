"""Shared HTTP machinery for the real source connectors.

GitHub has its own hand-written client (github/client.py) because its pagination and rate-limit
semantics are specific. The other five sources (Slack, Jira, Notion, Calendar, PagerDuty) share
the same needs — bearer/basic/token auth, retry with backoff on 429/5xx honoring Retry-After,
and per-page fetches — so that lives here once. Each source's connector implements only its own
pagination shape (cursor vs. offset vs. page-token) and object normalization on top of RestClient.

The HTTP transport, sleeper, and clock are injectable, so tests drive every path through an
httpx.MockTransport with no network and no wall-clock delay.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

import httpx

from cortex.platform.logging import get_logger
from cortex.platform.observability import METRICS

log = get_logger("cortex.ingestion.http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ConnectorAuthError(RuntimeError):
    """Raised when a connector has no usable credential."""


@runtime_checkable
class AuthProvider(Protocol):
    def header(self) -> str:
        """Return the full Authorization header value (scheme + credential)."""


class StaticAuth:
    """Fixed Authorization header: ``{scheme} {value}``.

    Covers Slack (``Bearer xoxb-...``), Notion (``Bearer secret_...``), Jira Cloud
    (``Basic base64(email:token)``) and PagerDuty (``Token token=...`` via scheme='Token',
    value='token=...').
    """

    def __init__(self, value: str, *, scheme: str = "Bearer") -> None:
        self._value = value
        self._scheme = scheme

    def header(self) -> str:
        if not self._value:
            raise ConnectorAuthError("empty credential")
        return f"{self._scheme} {self._value}"


class RestClient:
    """JSON REST client with retry/backoff and rate-limit handling.

    Retries 429/5xx and honors ``Retry-After`` (seconds); other 4xx raise immediately. Auth is
    an AuthProvider queried per request so refreshing tokens (Google OAuth) stay valid.
    """

    def __init__(
        self,
        auth: AuthProvider | None,
        *,
        base_url: str,
        source: str,
        http: httpx.Client | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int = 5,
        base_delay: float = 0.5,
        max_delay: float = 60.0,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._auth = auth
        self._base = base_url.rstrip("/")
        self._source = source
        self._http = http or httpx.Client(timeout=30.0)
        self._extra = headers or {}
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleeper
        self._clock = clock

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", **self._extra}
        if self._auth is not None:
            h["Authorization"] = self._auth.header()
        return h

    def get_json(self, path: str, *, params: dict | None = None) -> Any:
        return self.request("GET", self._url(path), params=params).json()

    def post_json(self, path: str, *, json: dict | None = None, params: dict | None = None) -> Any:
        return self.request("POST", self._url(path), params=params, json=json).json()

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self._base}{path}"

    def request(
        self, method: str, url: str, *, params: dict | None = None, json: dict | None = None
    ) -> httpx.Response:
        last: httpx.Response | None = None
        for attempt in range(1, self._max_retries + 1):
            resp = self._http.request(
                method, url, params=params, json=json, headers=self._headers()
            )
            METRICS.inc(
                "cortex_connector_requests_total",
                service="ingestion-service", source=self._source, status=str(resp.status_code),
            )
            if resp.status_code < 400:
                return resp
            if resp.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                delay = self._retry_delay(resp, attempt)
                METRICS.inc(
                    "cortex_connector_retries_total",
                    service="ingestion-service", source=self._source,
                )
                log.warning(
                    "connector request retry",
                    extra={"extra_fields": {
                        "source": self._source, "status": resp.status_code,
                        "attempt": attempt, "delay_s": round(delay, 3), "url": url,
                    }},
                )
                self._sleep(delay)
                last = resp
                continue
            resp.raise_for_status()
        assert last is not None
        last.raise_for_status()
        return last  # pragma: no cover - unreachable

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(float(retry_after), self._max_delay)
            except ValueError:
                pass
        ceiling = min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)
        return random.uniform(0, ceiling)


def parse_ts(value: Any) -> datetime:
    """Parse an ISO-8601 / epoch timestamp to an aware UTC datetime; now() on failure."""
    if value in (None, ""):
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # Slack ts like "1700000000.000100"
        try:
            return datetime.fromtimestamp(float(str(value).split(".")[0]), tz=timezone.utc)
        except (ValueError, OverflowError):
            return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def first_line(text: str | None) -> str | None:
    if not text:
        return None
    return text.splitlines()[0].strip() or None
