#!/usr/bin/env bash
# Build images and (re)deploy the requested groups. Volumes are preserved.
# Usage: setup-dev.sh [infra|runtime|service|<csv>]   (no arg → all groups)
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
parse_groups "${1:-}"
ensure_env_symlink

# Service first — postgres/redis live here and local-infra services
# (keycloak, litellm, temporal) reach them via host.docker.internal.
if has_group service; then
  echo "[service] building & starting services..."
  service_compose build
  service_compose up -d
fi

if has_group infra; then
  echo "[infra] building & starting local-infra..."
  infra_compose build
  infra_compose up -d
fi

if has_group runtime; then
  echo "[runtime] ensuring k3s is up..."
  infra_compose up -d k8s

  echo -n "[runtime] waiting for k3s api..."
  until k8s kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 2; done
  echo " ready."

  K8S_GATEWAY_IP=$(k8s ip route | awk '/default/ {print $3}' | head -1)
  collect_build_args

  echo "[runtime] building runtime images..."
  docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} \
    -t aviary-runtime:latest "$PROJECT_DIR/runtime/"
  docker save aviary-runtime:latest | k8s ctr images import -

  docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} \
    -f "$PROJECT_DIR/runtime/Dockerfile.custom" \
    -t aviary-runtime-custom:latest "$PROJECT_DIR/runtime/"
  docker save aviary-runtime-custom:latest | k8s ctr images import -

  echo "[runtime] applying helm charts..."
  render_chart aviary-platform    aviary-platform    values-dev.yaml    "$K8S_GATEWAY_IP" \
    | k8s kubectl apply -f -
  render_chart aviary-env-default aviary-environment values-dev.yaml    "$K8S_GATEWAY_IP" \
    | k8s kubectl apply -f -
  render_chart aviary-env-custom  aviary-environment values-custom.yaml "$K8S_GATEWAY_IP" \
    | k8s kubectl apply -f -

  echo "[runtime] restarting & waiting for rollout..."
  k8s kubectl -n agents rollout restart deploy/aviary-env-default deploy/aviary-env-custom
  k8s kubectl -n agents rollout status  deploy/aviary-env-default --timeout=180s
  k8s kubectl -n agents rollout status  deploy/aviary-env-custom  --timeout=180s
fi
