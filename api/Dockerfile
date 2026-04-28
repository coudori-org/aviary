FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv
COPY --from=curlimages/curl /usr/bin/curl /usr/bin/curl

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Node + npm/npx for probing stdio MCP servers declared in config.yaml.
# Pulled from the official image so air-gapped builds don't need NodeSource.
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Copy workspace layout for dependency resolution (cached layer)
COPY pyproject.toml uv.lock ./
COPY shared/pyproject.toml ./shared/pyproject.toml
COPY api/pyproject.toml ./api/pyproject.toml
COPY admin/pyproject.toml ./admin/pyproject.toml
COPY agent-supervisor/pyproject.toml ./agent-supervisor/pyproject.toml

# Shared source needed for workspace install
COPY shared/ ./shared/

# Install deps from lock file (cache-friendly — only reruns on manifest/lock change)
ARG UV_INDEX_URL
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --package aviary-api --no-dev --no-install-project

# Copy app source
COPY api/ ./api/
RUN uv sync --frozen --package aviary-api --no-dev

# Activate virtual environment via PATH
ENV PATH="/workspace/.venv/bin:$PATH"

WORKDIR /workspace/api

COPY api/entrypoint.sh /workspace/api/entrypoint.sh
RUN chmod +x /workspace/api/entrypoint.sh

EXPOSE 8000

CMD ["/workspace/api/entrypoint.sh"]
