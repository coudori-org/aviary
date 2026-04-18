# Shared helpers for scripts/. Source this from other scripts — don't execute.
#
# Usage:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   # shellcheck source=_common.sh
#   source "$SCRIPT_DIR/_common.sh"
#   load_env_and_build_args   # populates BUILD_ARGS from .env

if [ -n "${_AVIARY_COMMON_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
_AVIARY_COMMON_LOADED=1

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Populate BUILD_ARGS from .env (UV_INDEX_URL, NPM_CONFIG_REGISTRY). Callers
# pass "${BUILD_ARGS[@]}" to docker build.
load_env_and_build_args() {
  if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
  fi
  BUILD_ARGS=()
  [ -n "${UV_INDEX_URL:-}" ]        && BUILD_ARGS+=(--build-arg "UV_INDEX_URL=$UV_INDEX_URL")
  [ -n "${NPM_CONFIG_REGISTRY:-}" ] && BUILD_ARGS+=(--build-arg "NPM_CONFIG_REGISTRY=$NPM_CONFIG_REGISTRY")
  # The `[ -n "" ] && ...` pattern above returns 1 when env vars are unset.
  # Without this explicit success the function would propagate that 1 to
  # its caller and `set -e` would kill the script silently.
  return 0
}

# Load an image into the in-cluster K3s containerd.
load_k8s_image() {
  local image=$1
  docker save "$image" | docker compose exec -T k8s ctr images import -
}

# Resolve the K3s container's default gateway — the IP agents use to reach
# platform services (via the `k8s` hostname alias in docker-compose).
k8s_gateway_ip() {
  docker compose exec -T k8s ip route | awk '/default/ {print $3}' | head -1
}
