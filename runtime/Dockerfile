# --- Build stage: compile TypeScript ---
FROM node:22-slim AS build

ARG NPM_CONFIG_REGISTRY

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci

COPY tsconfig.json /app/
COPY src/ /app/src/
RUN npx tsc

# --- Runtime stage ---
FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates bubblewrap python3 python3-venv python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

ARG NPM_CONFIG_REGISTRY
RUN npm install -g @anthropic-ai/claude-code \
    && chmod +x /usr/local/lib/node_modules/@anthropic-ai/claude-code/vendor/ripgrep/*/rg

# Replace `claude` binary with bubblewrap sandbox wrapper.
# SDK invokes `claude` → wrapper → bwrap namespace → `claude-real`.
# This guarantees interception regardless of how the SDK resolves the binary.
RUN CLAUDE_BIN=$(which claude) && \
    mv "$CLAUDE_BIN" "$(dirname "$CLAUDE_BIN")/claude-real" && \
    cp /dev/null "$CLAUDE_BIN"
# Actual wrapper content copied below after COPY scripts/

WORKDIR /app
COPY package.json package-lock.json /app/
RUN npm ci --omit=dev

# Copy compiled JS from build stage (no TypeScript needed at runtime)
COPY --from=build /app/dist/ /app/dist/

COPY scripts/ /app/scripts/
COPY config/managed-settings.json /etc/claude-code/managed-settings.json

# Install the sandbox wrapper as the `claude` command
RUN CLAUDE_BIN=$(which claude-real) && \
    cp /app/scripts/claude-sandbox.sh "$(dirname "$CLAUDE_BIN")/claude" && \
    chmod +x "$(dirname "$CLAUDE_BIN")/claude"

# bwrap sandbox needs /workspace to exist as the bind target for
# $SESSION_WORKSPACE. /workspace-root is the K8s PVC mount point (created
# at pod startup); bwrap then tmpfs-masks it so sibling sessions living
# under the same PVC are invisible inside the sandbox.
RUN mkdir -p /workspace /artifacts

# Global git config — available inside bwrap via --ro-bind / /
RUN git config --system user.name "aviary" \
    && git config --system user.email "aviary-agent@aviary.com"

# Use built-in non-root `node` user (UID 1000)
# Claude Code CLI refuses --dangerously-skip-permissions as root
RUN chown -R node:node /app
USER node

EXPOSE 3000

CMD ["node", "dist/server.js"]
