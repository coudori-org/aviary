#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Quick Rebuild — only rebuild what changed
#
# Usage:
#   ./scripts/quick-rebuild.sh runtime       # Rebuild runtime image + load to K8s
#   ./scripts/quick-rebuild.sh controller    # Rebuild agent-controller + load to K8s
#   ./scripts/quick-rebuild.sh egress        # Rebuild egress-proxy + load to K8s
#   ./scripts/quick-rebuild.sh k8s           # All K8s images
#   ./scripts/quick-rebuild.sh compose       # Rebuild docker compose services
#   ./scripts/quick-rebuild.sh full          # docker compose down -v + setup-dev.sh
#   ./scripts/quick-rebuild.sh smoke         # Just run smoke test (no rebuild)
#
# Add --smoke to any command to run smoke test after rebuild:
#   ./scripts/quick-rebuild.sh runtime --smoke
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
NC='\033[0m'; BOLD='\033[1m'

TARGET="${1:-help}"
RUN_SMOKE=false

for arg in "$@"; do
  [ "$arg" = "--smoke" ] && RUN_SMOKE=true
done

load_k8s_image() {
  local image=$1
  echo -e "${CYAN}Loading ${image} into K8s...${NC}"
  docker save "$image" | docker compose exec -T k8s ctr images import -
  echo -e "${GREEN}✓ ${image} loaded${NC}"
}

rebuild_runtime() {
  echo -e "${BOLD}Rebuilding runtime...${NC}"
  docker build -t aviary-runtime:latest ./runtime/
  load_k8s_image "aviary-runtime:latest"
  echo -e "${CYAN}Rolling restart runtime pods...${NC}"
  docker compose exec -T k8s kubectl rollout restart deployment -l app=aviary-agent -A 2>/dev/null || true
}

rebuild_controller() {
  echo -e "${BOLD}Rebuilding agent-controller...${NC}"
  docker build -t aviary-agent-controller:latest -f controller/Dockerfile .
  load_k8s_image "aviary-agent-controller:latest"
  echo -e "${CYAN}Restarting controller deployment...${NC}"
  docker compose exec -T k8s kubectl rollout restart deployment/agent-controller -n platform
}

rebuild_egress() {
  echo -e "${BOLD}Rebuilding egress-proxy...${NC}"
  docker build -t aviary-egress-proxy:latest ./egress-proxy/
  load_k8s_image "aviary-egress-proxy:latest"
  echo -e "${CYAN}Restarting egress-proxy deployment...${NC}"
  docker compose exec -T k8s kubectl rollout restart deployment/egress-proxy -n platform
}

case "$TARGET" in
  runtime)
    rebuild_runtime
    ;;
  controller)
    rebuild_controller
    ;;
  egress)
    rebuild_egress
    ;;
  k8s)
    rebuild_runtime
    rebuild_controller
    rebuild_egress
    ;;
  compose)
    echo -e "${BOLD}Rebuilding compose services...${NC}"
    docker compose up -d --build
    ;;
  full)
    echo -e "${BOLD}Full rebuild (down -v + setup-dev.sh)...${NC}"
    docker compose down -v
    ./scripts/setup-dev.sh
    RUN_SMOKE=true
    ;;
  smoke)
    RUN_SMOKE=true
    ;;
  help|*)
    echo "Usage: $0 <target> [--smoke]"
    echo ""
    echo "Targets:"
    echo "  runtime      Rebuild runtime image + load to K8s + rolling restart"
    echo "  controller   Rebuild agent-controller + load to K8s + restart"
    echo "  egress       Rebuild egress-proxy + load to K8s + restart"
    echo "  k8s          All K8s images (runtime + controller + egress)"
    echo "  compose      Rebuild docker compose services (hot-reload)"
    echo "  full         Complete teardown + setup-dev.sh"
    echo "  smoke        Just run smoke test"
    echo ""
    echo "Options:"
    echo "  --smoke      Run smoke test after rebuild"
    exit 0
    ;;
esac

if [ "$RUN_SMOKE" = true ]; then
  echo ""
  echo -e "${BOLD}Running smoke test...${NC}"
  ./scripts/smoke-test.sh --no-cleanup
fi
