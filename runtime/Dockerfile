FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates bubblewrap \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required by claude-agent-sdk — it spawns Claude Code CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Replace `claude` binary with bubblewrap sandbox wrapper.
# SDK invokes `claude` → wrapper → bwrap namespace → `claude-real`.
# This guarantees interception regardless of how the SDK resolves the binary.
RUN CLAUDE_BIN=$(which claude) && \
    mv "$CLAUDE_BIN" "$(dirname "$CLAUDE_BIN")/claude-real" && \
    cp /dev/null "$CLAUDE_BIN"
# Actual wrapper content copied below after COPY scripts/

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/app/
COPY scripts/ /app/scripts/

# Install the sandbox wrapper as the `claude` command
RUN CLAUDE_BIN=$(which claude-real) && \
    cp /app/scripts/claude-sandbox.sh "$(dirname "$CLAUDE_BIN")/claude" && \
    chmod +x "$(dirname "$CLAUDE_BIN")/claude"

# Create non-root user (Claude Code CLI refuses --dangerously-skip-permissions as root)
RUN useradd -m -u 1000 aviary && \
    chown -R aviary:aviary /app
USER aviary

EXPOSE 3000

CMD ["python", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "3000"]
