#!/usr/bin/env bash
# Stop running containers / scale runtime to 0. Volumes preserved.
# Usage: stop-dev.sh [infra|runtime|service|<csv>]   (no arg → all groups)
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
parse_groups "${1:-}"

if has_group runtime; then
  if k3s_running; then
    echo "[runtime] scaling runtime to 0..."
    k8s kubectl -n agents scale deploy/aviary-env-default --replicas=0
    k8s kubectl -n agents scale deploy/aviary-env-custom  --replicas=0
  else
    echo "[runtime] k3s not running — nothing to stop"
  fi
fi

if has_group infra; then
  echo "[infra] stopping local-infra..."
  infra_compose stop
fi

if has_group service; then
  echo "[service] stopping services..."
  service_compose stop
fi
