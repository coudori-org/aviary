FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv
COPY --from=curlimages/curl /usr/bin/curl /usr/bin/curl

WORKDIR /workspace

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
RUN uv sync --frozen --package aviary-agent-supervisor --no-dev --no-install-project

# Copy app source
COPY agent-supervisor/ ./agent-supervisor/
RUN uv sync --frozen --package aviary-agent-supervisor --no-dev

# Activate virtual environment via PATH
ENV PATH="/workspace/.venv/bin:$PATH"

WORKDIR /workspace/agent-supervisor

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
