FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

WORKDIR /workspace

# Copy workspace layout for dependency resolution (cached layer)
COPY pyproject.toml uv.lock ./
COPY shared/pyproject.toml ./shared/pyproject.toml
COPY api/pyproject.toml ./api/pyproject.toml
COPY admin/pyproject.toml ./admin/pyproject.toml
COPY agent-supervisor/pyproject.toml ./agent-supervisor/pyproject.toml
COPY mcp-gateway/pyproject.toml ./mcp-gateway/pyproject.toml
COPY workflow-worker/pyproject.toml ./workflow-worker/pyproject.toml

# Shared source needed for workspace install
COPY shared/ ./shared/

ARG UV_INDEX_URL
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --package aviary-workflow-worker --no-dev --no-install-project

# Copy worker source
COPY workflow-worker/ ./workflow-worker/
RUN uv sync --frozen --package aviary-workflow-worker --no-dev

ENV PATH="/workspace/.venv/bin:$PATH"

WORKDIR /workspace/workflow-worker

CMD ["python", "-m", "worker.main"]
