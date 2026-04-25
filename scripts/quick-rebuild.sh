#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
NC='\033[0m'; BOLD='\033[1m'

TARGET="${1:-help}"
RUN_SMOKE=false
SMOKE_BACKEND=""

load_env_and_build_args

for arg in "$@"; do
  if [ "$arg" = "--smoke" ]; then
    RUN_SMOKE=true
  elif [ "${prev_arg:-}" = "--backend" ]; then
    SMOKE_BACKEND="$arg"
  fi
  prev_arg="$arg"
done

load_k8s_image_with_status() {
  local image=$1
  echo -e "${CYAN}Loading ${image} into K8s...${NC}"
  load_k8s_image "$image"
  echo -e "${GREEN}✓ ${image} loaded${NC}"
}

rebuild_runtime() {
  echo -e "${BOLD}Rebuilding runtime (+ custom variant)...${NC}"
  docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} -t aviary-runtime:latest "$PROJECT_DIR/runtime/"
  load_k8s_image_with_status "aviary-runtime:latest"
  docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} -f "$PROJECT_DIR/runtime/Dockerfile.custom" -t aviary-runtime-custom:latest "$PROJECT_DIR/runtime/"
  load_k8s_image_with_status "aviary-runtime-custom:latest"
  echo -e "${CYAN}Rolling restart runtime pods...${NC}"
  local_infra_compose --profile k3s exec -T k8s kubectl rollout restart deployment -n agents \
    -l aviary/role=agent-runtime 2>/dev/null || true
}

rebuild_agent_supervisor() {
  echo -e "${BOLD}Rebuilding agent-supervisor...${NC}"
  services_compose up -d --build supervisor
}

case "$TARGET" in
  runtime)
    rebuild_runtime
    ;;
  agent-supervisor)
    rebuild_agent_supervisor
    ;;
  services|compose)
    echo -e "${BOLD}Rebuilding all service images...${NC}"
    services_compose up -d --build
    ;;
  full)
    echo -e "${BOLD}Full rebuild (volumes preserved, K8s reset)...${NC}"
    services_compose down
    local_infra_compose --profile k3s down --remove-orphans
    docker volume rm aviary-local-infra_k8sdata 2>/dev/null || true
    "$SCRIPT_DIR/dev-up.sh"
    ;;
  full-clean)
    echo -e "${BOLD}Full clean rebuild (everything wiped)...${NC}"
    services_compose down -v
    local_infra_compose --profile k3s down -v --remove-orphans
    "$SCRIPT_DIR/dev-up.sh"
    ;;
  real)
    echo -e "${BOLD}Real (built) rebuild — volumes preserved, K8s reset...${NC}"
    services_compose down
    local_infra_compose --profile k3s down --remove-orphans
    docker volume rm aviary-local-infra_k8sdata 2>/dev/null || true
    "$SCRIPT_DIR/dev-up-real.sh"
    ;;
  smoke)
    RUN_SMOKE=true
    ;;
  help|*)
    cat <<'EOF'
Usage: ./scripts/quick-rebuild.sh <target> [--smoke --backend <name>]

Targets:
  runtime            Rebuild runtime image (K3s) + rolling restart
  agent-supervisor   Rebuild supervisor + restart
  services           Rebuild all service images (alias: compose)
  full               Full rebuild — preserves volumes (DB / Vault / chat / workspaces)
  full-clean         Full rebuild — wipes all volumes
  real               Full rebuild in built (prod-like) mode
  smoke              Just run smoke test
EOF
    exit 0
    ;;
esac

if [ "$RUN_SMOKE" = true ]; then
  if [ -z "$SMOKE_BACKEND" ]; then
    echo -e "${RED}ERROR:${NC} --backend <ollama|vllm> is required when running smoke test"
    exit 1
  fi
  echo ""
  echo -e "${BOLD}Running smoke test (backend=${SMOKE_BACKEND})...${NC}"
  "$SCRIPT_DIR/smoke-test.sh" --no-cleanup --backend "$SMOKE_BACKEND"
fi
