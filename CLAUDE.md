# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Google Analytics MCP (Model Context Protocol) server in Python. MCP servers expose tools/resources to AI assistants like Claude.

## Setup

Requires Python 3.12 (see `.python-version`). Uses `uv` for package management (standard for new Python projects with `pyproject.toml`).

```bash
uv sync          # install dependencies
uv add <pkg>     # add a dependency
```

## Common Commands

```bash
uv run python -m google_analytics_mcp   # run the MCP server
uv run pytest                           # run tests
uv run pytest tests/test_foo.py::test_bar  # run a single test
uv run ruff check .                     # lint
uv run ruff format .                    # format
```

## Architecture

This project is in early initialization — no source code exists yet. When built, it will follow MCP server conventions:

- The server will expose Google Analytics data as MCP tools/resources
- Entry point will likely be in `src/google_analytics_mcp/` or `google_analytics_mcp/`
- Authentication with Google Analytics API will require OAuth2 or service account credentials
