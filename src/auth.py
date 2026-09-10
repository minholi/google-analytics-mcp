"""
OAuth2 authentication for the Google Analytics 4 Data API.
All credentials are read from environment variables — never hard-coded.
"""

import os
from dataclasses import dataclass

import httpx

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
REQUIRED_ENV_VARS = [
    "GOOGLE_ANALYTICS_CLIENT_ID",
    "GOOGLE_ANALYTICS_CLIENT_SECRET",
    "GOOGLE_ANALYTICS_REFRESH_TOKEN",
]


@dataclass
class GoogleAnalyticsAuth:
    refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None

    # In-memory cache of the access token (valid ~1h)
    _access_token: str | None = None

    @classmethod
    def for_access_token(cls, access_token: str) -> "GoogleAnalyticsAuth":
        """Multi-tenant HTTP auth: use an access_token already issued by fastmcp.

        The fastmcp `GoogleProvider` stores the encrypted Google refresh_token
        and transparently refreshes the access_token before handing it here,
        so we don't need to know the refresh_token.
        """
        inst = cls()
        inst._access_token = access_token
        return inst

    @classmethod
    def from_env(cls) -> "GoogleAnalyticsAuth":
        """Build an instance from environment variables (stdio single-tenant mode)."""
        missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
        if missing:
            raise ValueError(
                f"Required environment variables not found: {', '.join(missing)}. "
                "Set them before starting the MCP server."
            )

        return cls(
            client_id=os.environ["GOOGLE_ANALYTICS_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_ANALYTICS_CLIENT_SECRET"],
            refresh_token=os.environ["GOOGLE_ANALYTICS_REFRESH_TOKEN"],
        )

    def get_access_token(self) -> str:
        """Return a valid access_token.

        If the token was already injected (multi-tenant HTTP flow via fastmcp),
        return it. Otherwise (stdio mode), exchange the refresh_token for a new
        access_token.
        """
        if self._access_token:
            return self._access_token

        if not (self.refresh_token and self.client_id and self.client_secret):
            raise ValueError("No access_token available and refresh credentials are missing.")

        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
            timeout=15,
        )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def invalidate_token(self) -> None:
        """Clear the cached access_token (use after a 401 in stdio mode)."""
        self._access_token = None

    def build_headers(self) -> dict[str, str]:
        """Default headers for GA4 Data API calls."""
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
        }
