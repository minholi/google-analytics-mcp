#!/usr/bin/env python3
"""
Interactive script to obtain the GOOGLE_ANALYTICS_REFRESH_TOKEN via OAuth2.

Prerequisites:
  1. Google Cloud project with the "Google Analytics Data API" enabled
  2. OAuth 2.0 credentials (Client ID and Client Secret) of type "Desktop app"
  3. A Google account with access to the target GA4 property

Usage:
  uv run python scripts/get_refresh_token.py
"""

import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

try:
    import httpx
except ImportError:
    print("❌ httpx is not installed. Run: uv sync")
    sys.exit(1)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

# Global to capture the code from the callback
_auth_code: str | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        global _auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Authorization complete.</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
            )
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Error: {error}".encode())

    def log_message(self, *args):  # silence server logs
        pass


def main():
    print("=" * 60)
    print("  Google Analytics OAuth2 — Refresh Token Generator")
    print("=" * 60)
    print()

    client_id = input("Client ID (from Google Cloud Console): ").strip()
    client_secret = input("Client Secret: ").strip()

    if not client_id or not client_secret:
        print("❌ Client ID and Client Secret are required.")
        sys.exit(1)

    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # ensure a refresh_token is returned
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(auth_params)}"

    print("\n🌐 Opening browser for authentication...")
    print(f"   If it doesn't open automatically, visit:\n   {auth_url}\n")
    webbrowser.open(auth_url)

    # Temporary local server on port 8080 to capture the callback
    print("⏳ Waiting for callback at http://localhost:8080/callback ...")
    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.handle_request()  # process a single request

    if not _auth_code:
        print("❌ Could not capture the authorization code.")
        sys.exit(1)

    print("✅ Authorization code received.")

    # Exchange the code for a refresh_token
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": _auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    tokens = response.json()

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("❌ Refresh token was not returned. Check that 'prompt=consent' is in the URL.")
        print(f"   Response: {tokens}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  ✅ Refresh Token obtained successfully!")
    print("=" * 60)
    print("\nAdd the following to your .env:\n")
    print(f"GOOGLE_ANALYTICS_CLIENT_ID={client_id}")
    print(f"GOOGLE_ANALYTICS_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_ANALYTICS_REFRESH_TOKEN={refresh_token}")
    print()
    print("⚠️  Keep the refresh token secure — it does not expire")
    print("   (unless manually revoked).")


if __name__ == "__main__":
    main()
