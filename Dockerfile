FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash mcp
WORKDIR /app

# Instala uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copia manifesto e instala dependências (layer cacheável)
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Copia código
COPY main.py .
COPY src/ ./src/

USER mcp

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

ENTRYPOINT ["uv", "run", "python", "main.py"]
CMD ["--transport", "http"]
