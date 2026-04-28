#!/usr/bin/env bash
# Apply the Helm charts to local K3s. Service compose stays for hot-reload dev;
# this is the chart-validation path.
# Usage: local-deploy.sh {setup [--only=...] [--skip=...] | start | stop | clean | logs <chart>}
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

DEPLOY_ORDER=(
  aviary-platform
  aviary-api
  aviary-supervisor
  aviary-admin
  aviary-workflow-worker
  aviary-env-default
  aviary-env-custom
  aviary-web
)

# The browser entry (Caddy) lives outside the cluster — see local-infra
# compose `proxy-k3s`. It hits web/api via NodePorts on host.docker.internal,
# mirroring the prod ALB → K8s Service target group topology.

# aviary-env-{default,custom} both render aviary-environment with different values.
chart_for() {
  case "$1" in
    aviary-env-default|aviary-env-custom) echo aviary-environment ;;
    *) echo "$1" ;;
  esac
}

values_for() {
  case "$1" in
    aviary-env-custom) echo values-custom.yaml ;;
    *) echo values-local.yaml ;;
  esac
}

ns_for() {
  case "$1" in
    aviary-env-default|aviary-env-custom) echo agents ;;
    *) echo platform ;;
  esac
}

declare -A IMAGE_FOR=(
  [aviary-api]="aviary-api:latest|api/Dockerfile|."
  [aviary-admin]="aviary-admin:latest|admin/Dockerfile|."
  [aviary-supervisor]="aviary-supervisor:latest|agent-supervisor/Dockerfile|."
  [aviary-workflow-worker]="aviary-workflow-worker:latest|workflow-worker/Dockerfile|."
  [aviary-env-default]="aviary-runtime:latest|runtime/Dockerfile|runtime"
  [aviary-env-custom]="aviary-runtime-custom:latest|runtime/Dockerfile.custom|runtime"
  [aviary-web]="aviary-web:k8s-local|web/Dockerfile|web"
)
MIGRATE_IMAGE="aviary-shared-migrate:latest|shared/Dockerfile|shared"

parse_setup_args() {
  ONLY_CHARTS=""
  SKIP_CHARTS=""
  for arg in "$@"; do
    case "$arg" in
      --only=*) ONLY_CHARTS=$(echo "${arg#--only=}" | tr ',' ' ') ;;
      --skip=*) SKIP_CHARTS=$(echo "${arg#--skip=}" | tr ',' ' ') ;;
      *) echo "unknown arg: $arg" >&2; exit 1 ;;
    esac
  done
}

ensure_k3s_up() {
  ensure_env_symlink
  ensure_config_yaml
  echo "[k3s] ensuring container is up..."
  infra_compose up -d k8s proxy-k3s
  echo -n "[k3s] waiting for api..."
  until k8s kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 2; done
  echo " ready."
  K8S_GATEWAY_IP=$(k8s ip route | awk '/default/ {print $3}' | head -1)
  export K8S_GATEWAY_IP
}

cmd_setup() {
  parse_setup_args "$@"
  ensure_k3s_up
  collect_build_args

  # Platform must land first — its externalServices proxy is what other charts dial.
  if is_selected aviary-platform; then
    echo "[platform] applying aviary-platform..."
    helm_apply aviary-platform aviary-platform values-local.yaml
  fi

  for chart in "${DEPLOY_ORDER[@]}"; do
    is_selected "$chart" || continue
    [ -n "${IMAGE_FOR[$chart]:-}" ] || continue
    IFS='|' read -r image dockerfile context extra <<<"${IMAGE_FOR[$chart]}"
    case "$chart" in
      aviary-web)
        # INTERNAL_API_URL is baked into routes-manifest.json by next.config.ts's
        # rewrites(). Browser-side URLs come from window.location at runtime.
        build_and_load_image "$image" "$dockerfile" "$context" \
          --target runner \
          --build-arg "INTERNAL_API_URL=http://aviary-api.platform.svc.cluster.local:8000"
        ;;
      *)
        build_and_load_image "$image" "$dockerfile" "$context"
        ;;
    esac
  done

  if is_selected aviary-api; then
    IFS='|' read -r image dockerfile context <<<"$MIGRATE_IMAGE"
    build_and_load_image "$image" "$dockerfile" "$context"
  fi

  # Seed aviary-config ConfigMap from project root config.yaml; api/supervisor mount it.
  if is_selected aviary-api || is_selected aviary-supervisor; then
    echo "[config] seeding aviary-config ConfigMap from config.yaml..."
    k8s kubectl create configmap aviary-config \
      --from-file=config.yaml=/dev/stdin \
      --namespace=platform \
      --dry-run=client -o yaml < "$PROJECT_DIR/config.yaml" \
      | k8s kubectl apply -f -
  fi

  for chart in "${DEPLOY_ORDER[@]}"; do
    [ "$chart" = "aviary-platform" ] && continue
    is_selected "$chart" || continue
    local chart_name; chart_name=$(chart_for "$chart")
    local values; values=$(values_for "$chart")
    echo "[apply] $chart  ($chart_name / $values)"
    helm_apply "$chart" "$chart_name" "$values"
  done

  if is_selected aviary-api; then
    echo "[wait] aviary-api-migrate Job..."
    k8s kubectl -n platform wait --for=condition=complete \
      job/aviary-api-migrate --timeout=180s || true
    wait_rollout platform aviary-api 300s
  fi
  is_selected aviary-supervisor       && wait_rollout platform aviary-supervisor || true
  is_selected aviary-admin            && wait_rollout platform aviary-admin || true
  is_selected aviary-workflow-worker  && wait_rollout platform aviary-workflow-worker || true
  is_selected aviary-env-default      && wait_rollout agents   aviary-env-default || true
  is_selected aviary-env-custom       && wait_rollout agents   aviary-env-custom || true
  is_selected aviary-web              && wait_rollout platform aviary-web || true

  print_summary
}

cmd_start() {
  k3s_running || { echo "k3s not running — run 'local-deploy.sh setup' first" >&2; exit 1; }
  for chart in "${DEPLOY_ORDER[@]}"; do
    [ "$chart" = "aviary-platform" ] && continue
    local ns; ns=$(ns_for "$chart")
    k8s kubectl -n "$ns" scale "deploy/$chart" --replicas=1 2>/dev/null || true
  done
}

cmd_stop() {
  k3s_running || { echo "k3s not running — nothing to stop"; return 0; }
  for chart in "${DEPLOY_ORDER[@]}"; do
    [ "$chart" = "aviary-platform" ] && continue
    local ns; ns=$(ns_for "$chart")
    k8s kubectl -n "$ns" scale "deploy/$chart" --replicas=0 2>/dev/null || true
  done
}

cmd_clean() {
  if ! k3s_running; then
    echo "k3s not running — nothing to clean"
    return 0
  fi
  K8S_GATEWAY_IP=$(k8s ip route | awk '/default/ {print $3}' | head -1)
  export K8S_GATEWAY_IP
  for ((i=${#DEPLOY_ORDER[@]}-1; i>=0; i--)); do
    local chart=${DEPLOY_ORDER[i]}
    local chart_name; chart_name=$(chart_for "$chart")
    local values; values=$(values_for "$chart")
    echo "[delete] $chart"
    helm_delete "$chart" "$chart_name" "$values"
  done
  k8s kubectl -n platform delete configmap aviary-config --ignore-not-found || true
}

cmd_logs() {
  local chart=${1:-}
  [ -n "$chart" ] || { echo "usage: local-deploy.sh logs <chart>" >&2; exit 1; }
  local ns; ns=$(ns_for "$chart")
  k8s kubectl -n "$ns" logs -f "deploy/$chart" --max-log-requests=10 --tail=200
}

print_summary() {
  cat <<EOF

[deploy] done.

  Browser:       http://localhost                (Caddy proxy → web + /api → api)
  Default rt:    http://localhost:30300
  Custom rt:     http://localhost:30301

  Logs:        ./scripts/local-deploy.sh logs aviary-api
EOF
}

main() {
  local cmd=${1:-}
  shift || true
  case "$cmd" in
    setup) cmd_setup "$@" ;;
    start) cmd_start "$@" ;;
    stop)  cmd_stop "$@" ;;
    clean) cmd_clean "$@" ;;
    logs)  cmd_logs "$@" ;;
    *)
      echo "usage: $0 {setup|start|stop|clean|logs} [args...]" >&2
      exit 1
      ;;
  esac
}

main "$@"
