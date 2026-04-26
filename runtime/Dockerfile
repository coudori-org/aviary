FROM node:22-slim AS build

ARG NPM_CONFIG_REGISTRY

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci

COPY tsconfig.json /app/
COPY src/ /app/src/
RUN npx tsc

FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates bubblewrap python3 python3-venv python-is-python3 \
    && rm -rf /var/lib/apt/lists/* \
    && chmod u+s /usr/bin/bwrap

ARG NPM_CONFIG_REGISTRY
RUN npm install -g @anthropic-ai/claude-code \
    && find /usr/local/lib/node_modules/@anthropic-ai/claude-code -name rg -type f -exec chmod +x {} +

RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Stash real binary; sandbox wrapper at /usr/local/bin/claude is installed below.
RUN CLAUDE_BIN=$(which claude) && \
    mv "$CLAUDE_BIN" "$(dirname "$CLAUDE_BIN")/claude-real" && \
    cp /dev/null "$CLAUDE_BIN"

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev

COPY --from=build /app/dist/ /app/dist/

COPY scripts/ /app/scripts/
COPY config/managed-settings.json /etc/claude-code/managed-settings.json

RUN CLAUDE_BIN=$(which claude-real) && \
    cp /app/scripts/claude-sandbox.sh "$(dirname "$CLAUDE_BIN")/claude" && \
    chmod +x "$(dirname "$CLAUDE_BIN")/claude"

# bwrap bind targets; workspace-root node-owned so fresh docker volumes inherit perms.
RUN mkdir -p /workspace /artifacts /workspace-root \
    && chown node:node /workspace-root

RUN git config --system user.name "aviary" \
    && git config --system user.email "aviary-agent@aviary.com"

# Non-root node user (UID 1000) required: Claude Code CLI refuses --dangerously-skip-permissions as root.
RUN chown -R node:node /app
USER node

EXPOSE 3000

CMD ["node", "dist/server.js"]
