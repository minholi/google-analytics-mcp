"""Shared fixtures for unit tests."""

from unittest.mock import patch

import pytest

from src.auth import GoogleAnalyticsAuth
from src.client import GoogleAnalyticsClient


@pytest.fixture
def stub_auth() -> GoogleAnalyticsAuth:
    """A GoogleAnalyticsAuth with an injected access token, bypassing OAuth."""
    return GoogleAnalyticsAuth.for_access_token(access_token="test-token")


@pytest.fixture
def client(stub_auth) -> GoogleAnalyticsClient:
    return GoogleAnalyticsClient(auth=stub_auth, property_id="123456789")


class FakeHttpxResponse:
    """Minimal httpx.Response stand-in for capture-and-return tests."""

    def __init__(self, json_body: dict, status_code: int = 200):
        self._json_body = json_body
        self.status_code = status_code
        self.text = str(json_body)

    def json(self) -> dict:
        return self._json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(f"{self.status_code}", request=None, response=None)


class FakeHttpxClient:
    """Captures the last POST body and returns a canned response."""

    def __init__(self, response_body: dict):
        self._response_body = response_body
        self.last_url: str | None = None
        self.last_json: dict | None = None
        self.last_headers: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return FakeHttpxResponse(self._response_body)


@pytest.fixture
def fake_httpx():
    """Factory that patches httpx.Client inside src.client with a FakeHttpxClient.

    Usage:
        def test_x(client, fake_httpx):
            captor = fake_httpx({"rows": [...]})
            client.get_overview(...)
            assert captor.last_json["dateRanges"] == [...]
    """
    captors: list[FakeHttpxClient] = []

    def _make(response_body: dict) -> FakeHttpxClient:
        captor = FakeHttpxClient(response_body)
        captors.append(captor)
        return captor

    with patch("src.client.httpx.Client") as mocked:
        # Every httpx.Client(...) call returns the most recently registered captor
        def _factory(*args, **kwargs):
            if not captors:
                raise RuntimeError(
                    "fake_httpx: register a response_body via the fixture before calling the client"
                )
            return captors[-1]

        mocked.side_effect = _factory
        yield _make
