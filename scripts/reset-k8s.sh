#!/usr/bin/env bash
set -euo pipefail
#
# Reset all agent runtime resources in the `agents` namespace while
# preserving per-agent PVC data (workspace + conversation history).
#
# Usage:
#   ./scripts/reset-k8s.sh           # Delete agent Deployments + Services
#   ./scripts/reset-k8s.sh --hard    # Also delete PVCs (full wipe)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

HARD=false
if [[ "${1:-}" == "--hard" ]]; then
    HARD=true
fi

echo "=== Agent Runtime Reset ==="

echo "[1/4] Deleting agent Deployments + Services in 'agents' namespace..."
docker compose exec -T k8s kubectl delete deployment,service -n agents \
  -l aviary/role=agent-runtime --ignore-not-found 2>/dev/null || true

if $HARD; then
    echo "[1b] Deleting agent PVCs (--hard)..."
    docker compose exec -T k8s kubectl delete pvc -n agents --all \
      --ignore-not-found 2>/dev/null || true
fi

echo "[2/4] Rebuilding runtime image..."
docker build -t aviary-runtime:latest ./runtime/

echo "[3/4] Loading image into K8s..."
docker save aviary-runtime:latest \
  | docker compose exec -T k8s ctr images import -

echo "[4/4] Restarting platform services..."
docker compose exec -T k8s kubectl rollout restart deployment -n platform \
  2>/dev/null || true

echo ""
echo "=== Reset complete ==="
if $HARD; then
    echo "All agent Deployments, Services, and PVCs deleted."
else
    echo "All agent Deployments and Services deleted. PVCs preserved."
fi
echo "Agents auto-register + activate on next chat message."
