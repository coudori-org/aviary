#!/usr/bin/env bash
# Remove the requested groups including volumes (full wipe).
# Usage: clean-dev.sh [infra|runtime|service|<csv>]   (no arg → all groups)
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
parse_groups "${1:-}"

# Services first; runtime needs k3s up; infra last so its volume wipe handles k3s.
if has_group service; then
  echo "[service] removing services and volumes..."
  service_compose down -v --remove-orphans
fi

if has_group runtime; then
  if k3s_running; then
    echo "[runtime] removing runtime resources..."
    K8S_GATEWAY_IP=$(k8s ip route | awk '/default/ {print $3}' | head -1)
    render_chart aviary-env-custom  aviary-environment values-custom.yaml "$K8S_GATEWAY_IP" \
      | k8s kubectl delete --ignore-not-found -f - || true
    render_chart aviary-env-default aviary-environment values-dev.yaml    "$K8S_GATEWAY_IP" \
      | k8s kubectl delete --ignore-not-found -f - || true
    render_chart aviary-platform    aviary-platform    values-dev.yaml    "$K8S_GATEWAY_IP" \
      | k8s kubectl delete --ignore-not-found -f - || true
  else
    echo "[runtime] k3s not running — skipping helm delete (volumes will be wiped if infra is included)"
  fi
fi

if has_group infra; then
  echo "[infra] removing local-infra and volumes..."
  infra_compose down -v --remove-orphans
fi
