#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Quick Rebuild — only rebuild what changed
#
# Usage:
#   ./scripts/quick-rebuild.sh runtime           # Rebuild runtime image (K3s) + rolling restart
#   ./scripts/quick-rebuild.sh agent-supervisor  # Rebuild supervisor (compose) + restart
#   ./scripts/quick-rebuild.sh compose          # Rebuild all docker compose services
#   ./scripts/quick-rebuild.sh full             # docker compose down + setup-dev.sh
#   ./scripts/quick-rebuild.sh smoke            # Just run smoke test
#
# Add --smoke --backend <name> to run smoke test after rebuild:
#   ./scripts/quick-rebuild.sh runtime --smoke --backend ollama
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"
cd "$PROJECT_DIR"

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
  docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} -t aviary-runtime:latest ./runtime/
  load_k8s_image_with_status "aviary-runtime:latest"
  # The custom variant layers on top of the base, so rebuild it too — any
  # change to the base should propagate to the `custom` environment.
  docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} -f ./runtime/Dockerfile.custom -t aviary-runtime-custom:latest ./runtime/
  load_k8s_image_with_status "aviary-runtime-custom:latest"
  echo -e "${CYAN}Rolling restart runtime pods...${NC}"
  docker compose exec -T k8s kubectl rollout restart deployment -n agents \
    -l aviary/role=agent-runtime 2>/dev/null || true
}

rebuild_agent_supervisor() {
  echo -e "${BOLD}Rebuilding agent-supervisor (docker compose)...${NC}"
  docker compose up -d --build supervisor
}

case "$TARGET" in
  runtime)
    rebuild_runtime
    ;;
  agent-supervisor)
    rebuild_agent_supervisor
    ;;
  compose)
    echo -e "${BOLD}Rebuilding compose services...${NC}"
    docker compose up -d --build
    ;;
  full)
    echo -e "${BOLD}Full rebuild (DB / Vault / chat history / session workspaces preserved, K8s reset)...${NC}"
    docker compose down
    docker volume rm "$(basename "$PROJECT_DIR")_k8sdata" 2>/dev/null || true
    ./scripts/setup-dev.sh
    ;;
  full-clean)
    echo -e "${BOLD}Full clean rebuild (everything wiped)...${NC}"
    docker compose down -v
    ./scripts/setup-dev.sh
    ;;
  smoke)
    RUN_SMOKE=true
    ;;
  help|*)
    echo "Usage: $0 <target> [--smoke]"
    echo ""
    echo "Targets:"
    echo "  runtime            Rebuild runtime image (K3s) + rolling restart"
    echo "  agent-supervisor   Rebuild supervisor (docker compose) + restart"
    echo "  compose            Rebuild all docker compose services (hot-reload)"
    echo "  full               Full rebuild — preserves DB, Vault, chat history, and session workspaces"
    echo "  full-clean         Full rebuild — wipes all volumes including chat history and workspaces"
    echo "  smoke              Just run smoke test"
    echo ""
    echo "Options:"
    echo "  --smoke              Run smoke test after rebuild (requires --backend)"
    echo "  --backend <name>     Inference backend for smoke test (ollama|vllm)"
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
  ./scripts/smoke-test.sh --no-cleanup --backend "$SMOKE_BACKEND"
fi
