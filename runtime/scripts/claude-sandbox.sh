#!/bin/bash
# Sandbox wrapper for the `claude` binary. SDK → wrapper → bwrap → claude-real.
# Mounts per-session workspace + per-(agent, session) venv into an isolated bwrap namespace.
# Runs unsandboxed if SESSION_WORKSPACE is unset (direct CLI usage).

set -euo pipefail

REAL_CLAUDE="$(dirname "$0")/claude-real"

if [ -z "${SESSION_WORKSPACE:-}" ]; then
    exec "$REAL_CLAUDE" "$@"
fi

mkdir -p "$SESSION_WORKSPACE"
mkdir -p "${SESSION_CLAUDE_DIR:?SESSION_CLAUDE_DIR must be set}"
mkdir -p "${SESSION_VENV_DIR:?SESSION_VENV_DIR must be set}"
mkdir -p "${SESSION_TMP:?SESSION_TMP must be set}"

VENV_HOST="$SESSION_VENV_DIR"
VENV_GUEST="/workspace/.venv"
# Created outside bwrap; rewrite shebangs/activate to the in-sandbox path so pip works post-bind.
if [ ! -x "$VENV_HOST/bin/python" ]; then
    rm -rf "$VENV_HOST"
    if python3 -m venv "$VENV_HOST" 2>/dev/null; then
        for f in "$VENV_HOST/bin"/pip* "$VENV_HOST/bin"/activate* "$VENV_HOST/bin"/Activate*; do
            [ -f "$f" ] && sed -i "s|$VENV_HOST|$VENV_GUEST|g" "$f"
        done
    fi
fi

VENV_ENV=()
VENV_BIND=()
if [ -x "$VENV_HOST/bin/python" ]; then
    VENV_ENV=(
        --setenv VIRTUAL_ENV "$VENV_GUEST"
        --setenv PATH "$VENV_GUEST/bin:$PATH"
        # Shared cache so sibling agents in the same session reuse fetched wheels.
        --setenv PIP_CACHE_DIR /workspace/.cache/pip
    )
    VENV_BIND=(--bind "$VENV_HOST" "$VENV_GUEST")
fi

# Optional workflow artifacts: read-only bind. Writes go through the save_as_artifact MCP tool only.
ARTIFACTS_BIND=()
if [ -n "${SESSION_ARTIFACTS_DIR:-}" ]; then
    mkdir -p "$SESSION_ARTIFACTS_DIR"
    ARTIFACTS_BIND=(--ro-bind "$SESSION_ARTIFACTS_DIR" /artifacts)
fi

exec bwrap \
    --ro-bind / / \
    --dev /dev \
    --proc /proc \
    --tmpfs /workspace-root \
    --bind "$SESSION_WORKSPACE" /workspace \
    --bind "$SESSION_CLAUDE_DIR" /workspace/.claude \
    "${VENV_BIND[@]}" \
    "${ARTIFACTS_BIND[@]}" \
    --bind "$SESSION_TMP" /tmp \
    --unshare-pid \
    --die-with-parent \
    --setenv HOME /workspace \
    "${VENV_ENV[@]}" \
    -- \
    "$REAL_CLAUDE" "$@"
