#!/usr/bin/env python3
"""Entry point for the Google Analytics MCP Server.

Modes:
  stdio  — Local Claude Desktop/Cursor, credentials via env vars (single-tenant).
  http   — Multi-tenant OAuth 2.1: each user authenticates against their own Google
           account via MCP's native OAuth flow (this server acts as AS + RS in the
           same process).
"""

import argparse
import logging
import os
import sys

logger = logging.getLogger("google_analytics_mcp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Analytics MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default=os.environ.get("MCP_TRANSPORT", "stdio")
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"))
    return parser.parse_args()


def check_env(transport: str) -> None:
    if transport == "stdio":
        required = [
            "GOOGLE_ANALYTICS_CLIENT_ID",
            "GOOGLE_ANALYTICS_CLIENT_SECRET",
            "GOOGLE_ANALYTICS_REFRESH_TOKEN",
        ]
    else:
        required = [
            "GOOGLE_OAUTH_WEB_CLIENT_ID",
            "GOOGLE_OAUTH_WEB_CLIENT_SECRET",
            "MCP_PUBLIC_URL",
        ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"❌ Required environment variables not set: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    args = parse_args()
    check_env(args.transport)

    from src.server import mcp

    if args.transport == "http":
        public_url = os.environ["MCP_PUBLIC_URL"].rstrip("/")
        app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)
        print(f"🚀 Google Analytics MCP at {public_url}/mcp", file=sys.stderr)
        meta_url = f"{public_url}/.well-known/oauth-authorization-server"
        print(f"   OAuth AS metadata: {meta_url}", file=sys.stderr)
        import uvicorn

        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    else:
        logger.info("Google Analytics MCP Server via stdio")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
