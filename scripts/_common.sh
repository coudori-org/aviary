# Source from other scripts — don't execute.

if [ -n "${_AVIARY_COMMON_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
_AVIARY_COMMON_LOADED=1

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_INFRA_DIR="$PROJECT_DIR/local-infra"
CHARTS_DIR="$PROJECT_DIR/charts"

local_infra_compose() {
  (cd "$LOCAL_INFRA_DIR" && docker compose "$@")
}
services_compose() {
  (cd "$PROJECT_DIR" && docker compose "$@")
}

load_env_and_build_args() {
  # Read only the build args we need; subshell sourcing keeps the rest of
  # each .env from leaking into the calling shell (and from there into
  # `docker compose`'s ${VAR:-default} interpolation).
  BUILD_ARGS=()
  local val
  for var in UV_INDEX_URL NPM_CONFIG_REGISTRY; do
    for env_file in "$PROJECT_DIR/.env" "$LOCAL_INFRA_DIR/.env"; do
      [ -f "$env_file" ] || continue
      # shellcheck disable=SC1090
      val=$(set -a; source "$env_file" 2>/dev/null; printf '%s' "${!var:-}")
      if [ -n "$val" ]; then
        BUILD_ARGS+=(--build-arg "$var=$val")
        break
      fi
    done
  done
  return 0
}

load_k8s_image() {
  local image=$1
  docker save "$image" | local_infra_compose --profile k3s exec -T k8s ctr images import -
}

k8s_gateway_ip() {
  local_infra_compose --profile k3s exec -T k8s ip route | awk '/default/ {print $3}' | head -1
}
