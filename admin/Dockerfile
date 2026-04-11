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
COPY agent-supervisor/pyproject.toml ./agent-supervisor/pyproject.toml

# Shared source needed for workspace install
COPY shared/ ./shared/

# Install deps from lock file
ARG UV_INDEX_URL
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --package aviary-admin --no-dev --no-install-project

# Copy app source
COPY admin/ ./admin/
RUN uv sync --frozen --package aviary-admin --no-dev

# Activate virtual environment via PATH
ENV PATH="/workspace/.venv/bin:$PATH"

WORKDIR /workspace/admin

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload", "--no-access-log"]
