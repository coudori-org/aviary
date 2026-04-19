#!/bin/bash
# claude-sandbox.sh — Drop-in replacement for the `claude` binary.
#
# This script IS the `claude` command. The real binary lives at `claude-real`.
# SDK invokes `claude` → hits this wrapper → bwrap namespace → `claude-real`.
#
# All per-agent / per-session directories live inside the single environment
# PVC (mounted at /workspace-root in the pod). The caller sets:
#   SESSION_WORKSPACE  = <PVC>/sessions/<sid>/shared               (session-wide, cross-agent)
#   SESSION_CLAUDE_DIR = <PVC>/sessions/<sid>/agents/<aid>/.claude (per-(agent,session))
#   SESSION_VENV_DIR   = <PVC>/sessions/<sid>/agents/<aid>/.venv   (per-(agent,session))
#   SESSION_TMP        = /tmp/<aid>_<sid>                          (pod-local, per-(agent,session))
#
# Bwrap then maps these onto the sandbox:
#   /workspace          ← SESSION_WORKSPACE   (shared across agents in the session)
#   /workspace/.claude  ← SESSION_CLAUDE_DIR  (per-agent CLI context)
#   /workspace/.venv    ← SESSION_VENV_DIR    (per-agent venv)
#   /tmp                ← SESSION_TMP         (per-agent temp)
#   PID namespace is isolated.
#
# Also bootstraps a per-(agent, session) Python venv at /workspace/.venv on
# the first turn so the agent can `pip install foo` and have packages persist
# across turns. Per-(agent, session) so concurrent pip installs from different
# agents on the same session can't corrupt a single venv.
#
# If SESSION_WORKSPACE is not set (e.g. direct CLI usage), runs without sandbox.

set -euo pipefail

REAL_CLAUDE="$(dirname "$0")/claude-real"

if [ -z "${SESSION_WORKSPACE:-}" ]; then
    exec "$REAL_CLAUDE" "$@"
fi

mkdir -p "$SESSION_WORKSPACE"
mkdir -p "${SESSION_CLAUDE_DIR:?SESSION_CLAUDE_DIR must be set}"
mkdir -p "${SESSION_VENV_DIR:?SESSION_VENV_DIR must be set}"
mkdir -p "${SESSION_TMP:?SESSION_TMP must be set}"

# ── Per-(agent, session) Python venv ──────────────────────────
# The venv lives on the per-agent PVC at $SESSION_VENV_DIR and is
# bwrap-bound to /workspace/.venv inside the sandbox. Per-agent (not
# shared) so concurrent pip installs from different agents on the same
# session can't corrupt a single venv. It's created OUTSIDE bwrap so its
# pip shebangs and activate scripts hard-code the host path — we rewrite
# those to the in-sandbox path so `pip` and `source activate` work
# correctly once bwrap remaps the mount.
VENV_HOST="$SESSION_VENV_DIR"
VENV_GUEST="/workspace/.venv"
# Treat the venv as missing unless it has a usable python — covers both
# "never created" and "empty mountpoint left over from a partial run".
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
        # pip download cache lives in the shared workspace so other
        # agents in the same session can reuse already-fetched wheels
        # without going back to the network.
        --setenv PIP_CACHE_DIR /workspace/.cache/pip
    )
    VENV_BIND=(--bind "$VENV_HOST" "$VENV_GUEST")
fi

# ── Workflow artifacts (optional, read-only) ──────────────────
# When the step belongs to a workflow run, SESSION_ARTIFACTS_DIR points at
# /workspace-root/workflows/<root_run_id>/artifacts on the PVC. We bind it
# read-only to /artifacts inside the sandbox so the agent can inspect any
# prior step's produced artifacts from the same run chain. Writes happen
# exclusively through the `save_as_artifact` MCP tool, which executes in
# the runtime process (outside the sandbox) and has direct FS access.
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
