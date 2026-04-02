FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy workspace layout for dependency resolution (cached layer)
COPY pyproject.toml uv.lock ./
COPY shared/pyproject.toml ./shared/pyproject.toml
COPY api/pyproject.toml ./api/pyproject.toml
COPY admin/pyproject.toml ./admin/pyproject.toml
COPY controller/pyproject.toml ./controller/pyproject.toml

# Shared source needed for workspace install
COPY shared/ ./shared/

# Install deps from lock file
ARG UV_INDEX_URL
RUN uv sync --frozen --package aviary-agent-controller --no-dev --no-install-project

# Copy app source
COPY controller/ ./controller/

RUN uv sync --frozen --package aviary-agent-controller --no-dev

WORKDIR /workspace/controller

EXPOSE 9000

CMD ["uv", "run", "--frozen", "--no-dev", "--package", "aviary-agent-controller", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
