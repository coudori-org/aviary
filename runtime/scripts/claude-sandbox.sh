#!/bin/bash
# claude-sandbox.sh — Drop-in replacement for the `claude` binary.
#
# This script IS the `claude` command. The real binary lives at `claude-real`.
# SDK invokes `claude` → hits this wrapper → bwrap namespace → `claude-real`.
#
# Creates a mount namespace where:
#   - / is the host filesystem (read-only)
#   - /workspace/sessions/ is an empty tmpfs (hides ALL sessions)
#   - $SESSION_WORKSPACE is bind-mounted back (only THIS session visible)
#   - /tmp is a fresh tmpfs
#   - PID namespace isolated
#
# If SESSION_WORKSPACE is not set (e.g. direct CLI usage), runs without sandbox.

set -euo pipefail

REAL_CLAUDE="$(dirname "$0")/claude-real"

if [ -z "${SESSION_WORKSPACE:-}" ]; then
    exec "$REAL_CLAUDE" "$@"
fi

if [ ! -d "$SESSION_WORKSPACE" ]; then
    mkdir -p "$SESSION_WORKSPACE"
fi

exec bwrap \
    --ro-bind / / \
    --dev /dev \
    --proc /proc \
    --tmpfs /tmp \
    --tmpfs /workspace/sessions \
    --bind "$SESSION_WORKSPACE" "$SESSION_WORKSPACE" \
    --unshare-pid \
    --die-with-parent \
    --setenv HOME /tmp \
    -- \
    "$REAL_CLAUDE" "$@"
