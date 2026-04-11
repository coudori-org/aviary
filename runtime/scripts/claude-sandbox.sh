#!/bin/bash
# claude-sandbox.sh — Drop-in replacement for the `claude` binary.
#
# This script IS the `claude` command. The real binary lives at `claude-real`.
# SDK invokes `claude` → hits this wrapper → bwrap namespace → `claude-real`.
#
# Creates a mount namespace where:
#   - / is the host filesystem (read-only)
#   - $SESSION_WORKSPACE (hostPath) is bind-mounted to /workspace (shared across agents)
#   - $SESSION_CLAUDE_DIR (PVC) is bind-mounted to /workspace/.claude (per-agent overlay)
#   - $SESSION_TMP is bind-mounted to /tmp (per-agent, NOT shared)
#   - PID namespace isolated
#
# Also bootstraps a per-session Python venv at /workspace/.venv on the
# first turn so the agent can `pip install foo` and have packages persist
# across turns within the session, while staying isolated from other
# sessions (each session has its own SESSION_WORKSPACE).
#
# If SESSION_WORKSPACE is not set (e.g. direct CLI usage), runs without sandbox.

set -euo pipefail

REAL_CLAUDE="$(dirname "$0")/claude-real"

if [ -z "${SESSION_WORKSPACE:-}" ]; then
    exec "$REAL_CLAUDE" "$@"
fi

mkdir -p "$SESSION_WORKSPACE"
mkdir -p "${SESSION_CLAUDE_DIR:?SESSION_CLAUDE_DIR must be set}"
mkdir -p "${SESSION_TMP:?SESSION_TMP must be set}"

# ── Per-session Python venv ───────────────────────────────────
# The venv lives in $SESSION_WORKSPACE/.venv (visible as /workspace/.venv
# inside the sandbox). It's created OUTSIDE bwrap so its pip shebangs and
# activate scripts hard-code the host path — we rewrite those to the
# in-sandbox path so `pip` and `source activate` work correctly once
# bwrap remaps the mount.
VENV_HOST="$SESSION_WORKSPACE/.venv"
VENV_GUEST="/workspace/.venv"
if [ ! -d "$VENV_HOST" ]; then
    if python3 -m venv "$VENV_HOST" 2>/dev/null; then
        for f in "$VENV_HOST/bin"/pip* "$VENV_HOST/bin"/activate* "$VENV_HOST/bin"/Activate*; do
            [ -f "$f" ] && sed -i "s|$VENV_HOST|$VENV_GUEST|g" "$f"
        done
    fi
fi

VENV_ENV=()
if [ -x "$VENV_HOST/bin/python" ]; then
    VENV_ENV=(
        --setenv VIRTUAL_ENV "$VENV_GUEST"
        --setenv PATH "$VENV_GUEST/bin:$PATH"
        --setenv PIP_CACHE_DIR /workspace/.cache/pip
    )
fi

# Ensure Node.js fetch() respects proxy env vars inside the sandbox.
if [ -f /app/scripts/proxy-bootstrap.js ] && [ -n "${HTTP_PROXY:-}" ]; then
    export NODE_OPTIONS="--require /app/scripts/proxy-bootstrap.js ${NODE_OPTIONS:-}"
fi

exec bwrap \
    --ro-bind / / \
    --dev /dev \
    --proc /proc \
    --tmpfs /workspace-shared \
    --bind "$SESSION_WORKSPACE" /workspace \
    --bind "$SESSION_CLAUDE_DIR" /workspace/.claude \
    --bind "$SESSION_TMP" /tmp \
    --unshare-pid \
    --die-with-parent \
    --setenv HOME /workspace \
    "${VENV_ENV[@]}" \
    -- \
    "$REAL_CLAUDE" "$@"
