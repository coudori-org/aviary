FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install deps from lock file
ARG UV_INDEX_URL
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
RUN uv sync --frozen --no-dev

# Activate virtual environment via PATH
ENV PATH="/app/.venv/bin:$PATH"

USER nobody
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
