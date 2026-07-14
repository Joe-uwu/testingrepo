"""Google OAuth token provider for the Calendar connector.

A Google API access token is short-lived (~1h). GoogleOAuthToken exchanges a long-lived
refresh token for a fresh access token on demand (POST https://oauth2.googleapis.com/token,
grant_type=refresh_token), caching it until shortly before expiry. Implements the AuthProvider
protocol (header()), so RestClient re-reads it per request and never sends a stale token.
"""

from __future__ import annotations

import time

import httpx

from cortex.services.ingestion.connectors._common import ConnectorAuthError

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleOAuthToken:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_url: str = GOOGLE_TOKEN_URL,
        http: httpx.Client | None = None,
        clock=time.time,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._token_url = token_url
        self._http = http or httpx.Client(timeout=30.0)
        self._clock = clock
        self._cached: tuple[str, float] | None = None  # (access_token, expiry_epoch)

    def access_token(self) -> str:
        now = self._clock()
        if self._cached and now < self._cached[1] - 60:
            return self._cached[0]
        resp = self._http.post(
            self._token_url,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ConnectorAuthError(data.get("error_description") or data["error"])
        token = data["access_token"]
        self._cached = (token, now + float(data.get("expires_in", 3600)))
        return token

    def header(self) -> str:
        return f"Bearer {self.access_token()}"
