FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash mcp
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy manifest and install dependencies (cacheable layer)
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Copy code and install the project into the venv
COPY main.py .
COPY src/ ./src/
RUN uv sync --no-dev

USER mcp

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/.well-known/oauth-authorization-server').raise_for_status()" || exit 1

ENTRYPOINT ["python", "main.py"]
CMD ["--transport", "http"]
