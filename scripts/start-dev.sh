#!/usr/bin/env bash
# Restart stopped containers / scale runtime back up. No build.
# Usage: start-dev.sh [infra|runtime|service|<csv>]   (no arg → all groups)
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
parse_groups "${1:-}"
ensure_env_symlink

if has_group service; then
  echo "[service] starting services..."
  service_compose start
fi

if has_group infra; then
  echo "[infra] starting local-infra..."
  infra_compose start
fi

if has_group runtime; then
  if k3s_running; then
    echo "[runtime] scaling runtime up..."
    k8s kubectl -n agents scale deploy/aviary-env-default --replicas=1
    k8s kubectl -n agents scale deploy/aviary-env-custom  --replicas=1
  else
    echo "[runtime] k3s not running — start infra first (or run setup-dev.sh runtime)" >&2
    exit 1
  fi
fi
