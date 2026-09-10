# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working with this repository.

## Project Overview

An MCP (Model Context Protocol) server exposing the Google Analytics 4 Data API to AI agents. Two transports:

- **stdio** — single-tenant, credentials in `.env` (used by Claude Desktop / Cursor locally).
- **HTTP multi-tenant** — each user authenticates via OAuth 2.1 through fastmcp's `GoogleProvider`, which persists an encrypted per-user Google refresh token.

## Setup

Python 3.12 (see `.python-version`). `uv` for package management.

```bash
uv sync          # install dependencies
uv add <pkg>     # add a runtime dependency
uv add --dev <pkg>   # add a dev dependency
```

## Common commands

```bash
uv run python main.py --transport stdio   # local MCP server
docker compose up -d --build              # HTTP multi-tenant server
uv run pytest                             # run tests
uv run pytest tests/test_client_queries.py::test_get_overview  # single test
uv run ruff check .                       # lint
uv run ruff format .                      # format
```

## Architecture

- `main.py` — argparse + `load_dotenv()`; picks stdio or HTTP; HTTP path builds `mcp.http_app(...)` and runs under uvicorn.
- `src/server.py` — `_build_fastmcp()` conditionally wires `GoogleProvider` when `MCP_PUBLIC_URL` is set; exposes 8 tools; `_get_client()` factory reads `get_access_token()` from the fastmcp context (HTTP) or falls back to env vars (stdio).
- `src/auth.py` — `GoogleAnalyticsAuth` dataclass with `from_env()` (stdio: refresh-token exchange) and `for_access_token()` (HTTP: token injected by fastmcp).
- `src/client.py` — direct `httpx` REST calls to `analyticsdata.googleapis.com/v1beta`, with 401-retry.
- `src/formatters.py` — markdown table rendering; JSON path bypasses these and returns raw dicts.
- `scripts/get_refresh_token.py` — interactive OAuth wizard for stdio setup.

## Tests

`tests/` uses pytest with `asyncio_mode="auto"`. Client tests build request bodies with mocked httpx responses; formatter tests assert English labels and structure.

## Publishing

Public repo: `github.com/minholi/google-analytics-mcp`. GitLab kept as secondary remote (`gitlab`). MIT licensed.
