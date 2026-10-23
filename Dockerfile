FROM ghcr.io/astral-sh/uv:0.12.3 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY data ./data
COPY scripts ./scripts
RUN groupadd --gid 10001 agent && useradd --uid 10001 --gid agent --create-home agent && mkdir /app/runtime && chown agent:agent /app/runtime
USER agent
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=8s --start-period=60s CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=6)"]
CMD ["/app/.venv/bin/python","-m","uvicorn","app.api:app","--host","0.0.0.0","--port","8000","--workers","1","--proxy-headers","--forwarded-allow-ips","*"]
