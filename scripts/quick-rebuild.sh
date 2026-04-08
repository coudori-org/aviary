#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Quick Rebuild — only rebuild what changed
#
# Usage:
#   ./scripts/quick-rebuild.sh runtime           # Rebuild runtime image + load to K8s
#   ./scripts/quick-rebuild.sh agent-supervisor  # Rebuild agent-supervisor + load to K8s
#   ./scripts/quick-rebuild.sh egress            # Rebuild egress-proxy + load to K8s
#   ./scripts/quick-rebuild.sh k8s              # All K8s images
#   ./scripts/quick-rebuild.sh compose          # Rebuild docker compose services
#   ./scripts/quick-rebuild.sh full             # docker compose down -v + setup-dev.sh
#   ./scripts/quick-rebuild.sh smoke            # Just run smoke test
#
# Add --smoke --backend <name> to run smoke test after rebuild:
#   ./scripts/quick-rebuild.sh runtime --smoke --backend ollama
# ─────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
NC='\033[0m'; BOLD='\033[1m'

TARGET="${1:-help}"
RUN_SMOKE=false
SMOKE_BACKEND=""

# Load .env for registry settings (UV_INDEX_URL, NPM_CONFIG_REGISTRY)
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

# Collect --build-arg flags from registry env vars
BUILD_ARGS=()
[ -n "${UV_INDEX_URL:-}" ]        && BUILD_ARGS+=(--build-arg "UV_INDEX_URL=$UV_INDEX_URL")
[ -n "${NPM_CONFIG_REGISTRY:-}" ] && BUILD_ARGS+=(--build-arg "NPM_CONFIG_REGISTRY=$NPM_CONFIG_REGISTRY")

for arg in "$@"; do
  if [ "$arg" = "--smoke" ]; then
    RUN_SMOKE=true
  elif [ "${prev_arg:-}" = "--backend" ]; then
    SMOKE_BACKEND="$arg"
  fi
  prev_arg="$arg"
done

load_k8s_image() {
  local image=$1
  echo -e "${CYAN}Loading ${image} into K8s...${NC}"
  docker save "$image" | docker compose exec -T k8s ctr images import -
  echo -e "${GREEN}✓ ${image} loaded${NC}"
}

rebuild_runtime() {
  echo -e "${BOLD}Rebuilding runtime...${NC}"
  docker build "${BUILD_ARGS[@]}" -t aviary-runtime:latest ./runtime/
  load_k8s_image "aviary-runtime:latest"
  echo -e "${CYAN}Rolling restart runtime pods...${NC}"
  docker compose exec -T k8s sh -c \
    'for ns in $(kubectl get ns -l aviary/managed=true -o name 2>/dev/null); do
       kubectl rollout restart deployment -n "${ns#namespace/}" 2>/dev/null || true
     done' 2>/dev/null || true
}

rebuild_agent_supervisor() {
  echo -e "${BOLD}Rebuilding agent-supervisor...${NC}"
  docker build "${BUILD_ARGS[@]}" -t aviary-agent-supervisor:latest -f agent-supervisor/Dockerfile .
  load_k8s_image "aviary-agent-supervisor:latest"
  echo -e "${CYAN}Restarting agent-supervisor deployment...${NC}"
  docker compose exec -T k8s kubectl rollout restart deployment/agent-supervisor -n platform
}

rebuild_egress() {
  echo -e "${BOLD}Rebuilding egress-proxy...${NC}"
  docker build "${BUILD_ARGS[@]}" -t aviary-egress-proxy:latest ./egress-proxy/
  load_k8s_image "aviary-egress-proxy:latest"
  echo -e "${CYAN}Restarting egress-proxy deployment...${NC}"
  docker compose exec -T k8s kubectl rollout restart deployment/egress-proxy -n platform
}

case "$TARGET" in
  runtime)
    rebuild_runtime
    ;;
  agent-supervisor)
    rebuild_agent_supervisor
    ;;
  egress)
    rebuild_egress
    ;;
  k8s)
    rebuild_runtime
    rebuild_agent_supervisor
    rebuild_egress
    ;;
  compose)
    echo -e "${BOLD}Rebuilding compose services...${NC}"
    docker compose up -d --build
    ;;
  full)
    echo -e "${BOLD}Full rebuild (DB preserved, K8s reset)...${NC}"
    docker compose down
    # Remove K8s volume (image cache + cluster state) but preserve DB
    docker volume rm "$(basename "$PROJECT_DIR")_k8sdata" 2>/dev/null || true
    ./scripts/setup-dev.sh
    ;;
  full-clean)
    echo -e "${BOLD}Full clean rebuild (DB + volumes wiped)...${NC}"
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
    echo "  runtime            Rebuild runtime image + load to K8s + rolling restart"
    echo "  agent-supervisor   Rebuild agent-supervisor + load to K8s + restart"
    echo "  egress             Rebuild egress-proxy + load to K8s + restart"
    echo "  k8s                All K8s images (runtime + agent-supervisor + egress)"
    echo "  compose            Rebuild docker compose services (hot-reload)"
    echo "  full               Full rebuild, DB preserved"
    echo "  full-clean         Full rebuild, DB + volumes wiped"
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
