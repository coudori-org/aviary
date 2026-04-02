FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install deps from lock file
ARG UV_INDEX_URL
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/

RUN uv sync --frozen --no-dev

USER nobody
EXPOSE 8080

CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
