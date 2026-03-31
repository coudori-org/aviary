#!/usr/bin/env bash
set -euo pipefail
#
# Reset all K8s agent resources while preserving PVC data.
#
# Deletes: Deployments, Services, Pods (they'll be recreated on next message)
# Preserves: PVCs (workspace data, conversation history)
# Also: resets deployment_active=false in the DB so the API knows to recreate.
#
# Usage:
#   ./scripts/reset-k8s.sh           # Reset agent pods + reload images
#   ./scripts/reset-k8s.sh --hard    # Also delete PVCs (full wipe)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

HARD=false
if [[ "${1:-}" == "--hard" ]]; then
    HARD=true
fi

echo "=== K8s Agent Reset ==="

# 1. Delete all agent Deployments and Services (not PVCs)
echo "[1/5] Cleaning agent namespaces..."
AGENT_NS=$(docker compose exec -T k3s kubectl get ns -l aviary/managed=true -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
for ns in $AGENT_NS; do
    echo "  $ns: deleting Deployment + Service..."
    docker compose exec -T k3s kubectl delete deployment --all -n "$ns" --ignore-not-found 2>/dev/null || true
    docker compose exec -T k3s kubectl delete service agent-runtime-svc -n "$ns" --ignore-not-found 2>/dev/null || true
    if $HARD; then
        echo "  $ns: deleting PVCs (--hard)..."
        docker compose exec -T k3s kubectl delete pvc --all -n "$ns" --ignore-not-found 2>/dev/null || true
    fi
done
echo "  Done. $(echo "$AGENT_NS" | wc -w) namespace(s) cleaned."

# 2. Reset deployment_active in DB
echo "[2/5] Resetting deployment_active flags in database..."
docker compose exec -T postgres psql -U aviary -d aviary -c \
    "UPDATE agents SET deployment_active = false WHERE deployment_active = true;" 2>/dev/null || true

# 3. Rebuild and reload K8s images
echo "[3/5] Building K8s images..."
docker build -t aviary-runtime:latest          ./runtime/
docker build -t aviary-inference-router:latest  ./inference-router/
docker build -t aviary-credential-proxy:latest  ./credential-proxy/
docker build -t aviary-egress-proxy:latest      ./egress-proxy/

echo "[4/5] Loading images into K3s..."
docker save \
  aviary-runtime:latest \
  aviary-inference-router:latest \
  aviary-credential-proxy:latest \
  aviary-egress-proxy:latest \
  | docker compose exec -T k3s ctr images import -

# 5. Restart platform deployments to pick up new images
echo "[5/5] Restarting platform services..."
docker compose exec -T k3s kubectl rollout restart deployment -n platform 2>/dev/null || true

echo ""
echo "=== Reset complete ==="
echo ""
if $HARD; then
    echo "All agent Deployments, Services, and PVCs deleted."
else
    echo "All agent Deployments and Services deleted. PVCs preserved."
fi
echo "Agents will auto-recreate pods on next chat message (lazy strategy)."
echo ""
echo "To manually force a specific agent's pod restart:"
echo "  curl -X POST http://localhost:8000/api/agents/{id}/activate"
