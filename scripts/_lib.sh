# Shared helpers for setup/clean/start/stop/logs scripts. Sourced, not run.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_INFRA_DIR="$PROJECT_DIR/local-infra"
CHARTS_DIR="$PROJECT_DIR/charts"
HELM_IMAGE="alpine/helm:3.14.4"

VALID_GROUPS=(infra runtime service)

infra_compose()   { (cd "$LOCAL_INFRA_DIR" && docker compose --profile k3s "$@"); }
service_compose() { (cd "$PROJECT_DIR"     && docker compose "$@"); }
k8s()             { infra_compose exec -T k8s "$@"; }

ensure_env_symlink() {
  if [ ! -L "$LOCAL_INFRA_DIR/.env" ]; then
    rm -f "$LOCAL_INFRA_DIR/.env"
    ln -s ../.env "$LOCAL_INFRA_DIR/.env"
  fi
}

parse_groups() {
  local raw="${1:-}"
  if [ -z "$raw" ]; then
    _GROUPS=("${VALID_GROUPS[@]}")
    return
  fi
  IFS=',' read -ra _GROUPS <<< "$raw"
  for g in "${_GROUPS[@]}"; do
    case "$g" in
      infra|runtime|service) ;;
      *) echo "unknown group: $g (valid: ${VALID_GROUPS[*]})" >&2; exit 1 ;;
    esac
  done
}

has_group() {
  local target=$1
  for g in "${_GROUPS[@]}"; do [ "$g" = "$target" ] && return 0; done
  return 1
}

k3s_running() {
  infra_compose ps --status running --services 2>/dev/null | grep -qx k8s
}

# Render a helm chart locally via the alpine/helm image. Echoes the manifest.
render_chart() {
  local release=$1 chart=$2 values=$3 gateway_ip=$4
  docker run --rm -v "$CHARTS_DIR:/charts:ro" "$HELM_IMAGE" template \
    "$release" "/charts/$chart" -f "/charts/$chart/$values" \
    --set hostGatewayIP="$gateway_ip"
}

# Build args from root .env (UV_INDEX_URL / NPM_CONFIG_REGISTRY only).
collect_build_args() {
  BUILD_ARGS=()
  [ -f "$PROJECT_DIR/.env" ] || return 0
  for v in UV_INDEX_URL NPM_CONFIG_REGISTRY; do
    val=$(set -a; source "$PROJECT_DIR/.env" 2>/dev/null; printf '%s' "${!v:-}")
    if [ -n "$val" ]; then BUILD_ARGS+=(--build-arg "$v=$val"); fi
  done
}
