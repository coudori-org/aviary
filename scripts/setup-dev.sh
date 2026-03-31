#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Aviary Dev Environment Setup ==="

# 1. Build and start all Docker Compose services
echo "[1/7] Building and starting Docker Compose services..."
docker compose up -d --build

# 2. Wait for PostgreSQL
echo "[2/7] Waiting for PostgreSQL..."
until docker compose exec -T postgres pg_isready -U aviary > /dev/null 2>&1; do
  sleep 1
done
echo "  PostgreSQL is ready."

# 3. Wait for Keycloak
echo "[3/7] Waiting for Keycloak..."
until curl -sf http://localhost:8080/realms/aviary/.well-known/openid-configuration > /dev/null 2>&1; do
  sleep 2
done
echo "  Keycloak is ready."

# 4. Wait for K8s + extract kubeconfig
echo "[4/7] Waiting for K8s..."
until docker compose exec -T k8s kubectl get nodes 2>/dev/null | grep -q " Ready"; do
  sleep 2
done
echo "  K8s is ready."

echo "  Extracting kubeconfig for API container..."
docker compose cp k8s:/etc/rancher/k3s/k3s.yaml ./api/kubeconfig.yaml
sed -i 's|127.0.0.1|k8s|g' ./api/kubeconfig.yaml
echo "  kubeconfig saved to api/kubeconfig.yaml"

# Resolve K8s gateway IP (docker host as seen from K8s cluster)
K8S_GATEWAY_IP=$(docker compose exec -T k8s ip route | awk '/default/ {print $3}' | head -1)
echo "  K8s gateway IP: $K8S_GATEWAY_IP"

# 5. Build K8s images and load them (runtime + egress-proxy only)
echo "[5/7] Building K8s images (runtime, egress-proxy)..."
docker build -t aviary-runtime:latest      ./runtime/
docker build -t aviary-egress-proxy:latest ./egress-proxy/

echo "  Loading images into K8s..."
docker save \
  aviary-runtime:latest \
  aviary-egress-proxy:latest \
  | docker compose exec -T k8s ctr images import -
echo "  All images loaded."

# 6. Apply K8s platform manifests (namespace first, then the rest)
echo "[6/7] Applying K8s platform resources..."
docker compose exec -T k8s kubectl apply -f - < ./k8s/platform/namespace.yaml
for f in ./k8s/platform/*.yaml; do
  [ "$(basename "$f")" = "namespace.yaml" ] && continue
  HOST_GATEWAY_IP="$K8S_GATEWAY_IP" envsubst '${HOST_GATEWAY_IP}' < "$f" \
    | docker compose exec -T k8s kubectl apply -f -
done
# Restart platform pods to pick up freshly loaded images
docker compose exec -T k8s kubectl rollout restart deployment -n platform 2>/dev/null || true
echo "  Platform namespace ready."

# 7. Wait for application services
echo "[7/7] Waiting for application services..."
echo -n "  Inference router..."
until curl -sf http://localhost:8090/health > /dev/null 2>&1; do
  sleep 2
done
echo " ready."
echo -n "  Credential proxy..."
until curl -sf http://localhost:8091/health > /dev/null 2>&1; do
  sleep 2
done
echo " ready."
echo -n "  API server..."
until curl -sf http://localhost:8000/api/health > /dev/null 2>&1; do
  sleep 2
done
echo " ready."
echo -n "  Web UI..."
until curl -sf http://localhost:3000 > /dev/null 2>&1; do
  sleep 2
done
echo " ready."

echo ""
echo "=== Dev environment is ready! ==="
echo ""
echo "Application:"
echo "  Web UI:            http://localhost:3000"
echo "  API Server:        http://localhost:8000"
echo "  API Health:        http://localhost:8000/api/health"
echo ""
echo "Platform Services:"
echo "  Inference Router:  http://localhost:8090"
echo "  Credential Proxy:  http://localhost:8091"
echo ""
echo "Infrastructure:"
echo "  PostgreSQL:  localhost:5432  (aviary/aviary)"
echo "  Redis:       localhost:6379"
echo "  Keycloak:    http://localhost:8080  (admin/admin)"
echo "  Vault:       http://localhost:8200  (token: dev-root-token)"
echo "  K8s API:     https://localhost:6443"
echo ""
echo "Test users (Keycloak):"
echo "  admin@test.com / password  (platform_admin, team: engineering)"
echo "  user1@test.com / password  (regular_user,   team: engineering, product)"
echo "  user2@test.com / password  (regular_user,   team: data-science)"
echo ""
echo "Hot reload:"
echo "  Edit files in api/, web/, inference-router/, or credential-proxy/"
echo "  — changes apply automatically via bind-mount."
echo "  If you change dependencies:"
echo "    docker compose up -d --build <service>"
echo "  To rebuild K8s images (runtime, egress-proxy):"
echo "    docker build -t aviary-runtime:latest ./runtime/"
echo "    docker build -t aviary-egress-proxy:latest ./egress-proxy/"
echo "    docker save aviary-runtime:latest aviary-egress-proxy:latest | docker compose exec -T k8s ctr images import -"
echo "    docker compose exec -T k8s kubectl rollout restart deployment -n platform"
