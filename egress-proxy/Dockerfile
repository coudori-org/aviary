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
EXPOSE 8080 8081

CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "app.main"]
