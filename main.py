#!/usr/bin/env python3
"""
Ponto de entrada do Google Analytics MCP Server (com autenticação por API Key).

Uso:
  # HTTP para equipes (autenticado):
  MCP_TRANSPORT=http python main.py

  # stdio local sem autenticação de rede (Claude Desktop / Cursor):
  python main.py --transport stdio
"""

import argparse
import logging
import os
import sys

logger = logging.getLogger("google_analytics_mcp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Analytics MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"],
                        default=os.environ.get("MCP_TRANSPORT", "stdio"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"))
    return parser.parse_args()


def check_env() -> None:
    required = [
        "GOOGLE_ANALYTICS_CLIENT_ID",
        "GOOGLE_ANALYTICS_CLIENT_SECRET",
        "GOOGLE_ANALYTICS_REFRESH_TOKEN",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"❌ Variáveis obrigatórias não definidas: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("GOOGLE_ANALYTICS_PROPERTY_ID"):
        print("⚠️  GOOGLE_ANALYTICS_PROPERTY_ID não definido — passe em cada chamada.", file=sys.stderr)


def build_http_app(mcp_server, key_store):
    """Envolve a app ASGI do FastMCP com middleware de autenticação."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    from starlette.routing import Mount

    class ApiKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path in ("/health", "/"):
                return await call_next(request)

            raw_key = (
                request.headers.get("X-API-Key")
                or _extract_bearer(request.headers.get("Authorization", ""))
            )
            if not raw_key:
                logger.warning(f"Sem API Key: {request.client.host} -> {request.url.path}")
                return JSONResponse(
                    {"error": "API Key obrigatória. Use o header X-API-Key ou Authorization: Bearer <key>."},
                    status_code=401,
                )
            entry = key_store.authenticate(raw_key)
            if entry is None:
                logger.warning(f"API Key inválida: {request.client.host} -> {request.url.path}")
                return JSONResponse({"error": "API Key inválida ou expirada."}, status_code=403)

            request.state.mcp_user = entry.user
            logger.info(f"[{entry.user}] {request.method} {request.url.path}")
            return await call_next(request)

    def _extract_bearer(auth_header: str) -> str:
        return auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""

    mcp_app = mcp_server.http_app(path="/mcp")
    return Starlette(routes=[Mount("/", app=mcp_app)],
                     middleware=[Middleware(ApiKeyMiddleware)])


def main() -> None:
    args = parse_args()
    check_env()

    from src.server import mcp

    if args.transport == "http":
        from src.auth_middleware import KeyStore
        key_store = KeyStore.from_env()
        if not key_store.list_users():
            print("⚠️  Nenhuma API Key configurada — servidor ABERTO.\n"
                  "   Defina ALLOWED_API_KEYS ou MCP_API_KEY no .env.", file=sys.stderr)

        app = build_http_app(mcp, key_store)
        print(f"🚀 Google Analytics MCP em http://{args.host}:{args.port}/mcp", file=sys.stderr)
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    else:
        logger.info("Google Analytics MCP Server via stdio")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
