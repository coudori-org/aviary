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

# 4. Wait for K3s + extract kubeconfig
echo "[4/7] Waiting for K3s..."
until docker compose exec -T k3s kubectl get nodes 2>/dev/null | grep -q " Ready"; do
  sleep 2
done
echo "  K3s is ready."

echo "  Extracting kubeconfig for API container..."
docker compose cp k3s:/etc/rancher/k3s/k3s.yaml ./api/kubeconfig.yaml
sed -i 's|127.0.0.1|k3s|g' ./api/kubeconfig.yaml
echo "  kubeconfig saved to api/kubeconfig.yaml"

# 5. Build ALL K3s images and load them in one pass
echo "[5/7] Building K3s images (runtime, inference-router, credential-proxy, egress-proxy)..."
docker build -t aviary-runtime:latest          ./runtime/
docker build -t aviary-inference-router:latest  ./inference-router/
docker build -t aviary-credential-proxy:latest  ./credential-proxy/
docker build -t aviary-egress-proxy:latest      ./egress-proxy/

echo "  Loading images into K3s..."
docker save \
  aviary-runtime:latest \
  aviary-inference-router:latest \
  aviary-credential-proxy:latest \
  aviary-egress-proxy:latest \
  | docker compose exec -T k3s ctr images import -
echo "  All images loaded."

# 6. Apply K8s platform manifests (namespace first, then the rest)
echo "[6/7] Applying K8s platform resources..."
docker compose exec -T k3s kubectl apply -f - < ./k8s/platform/namespace.yaml
for f in ./k8s/platform/*.yaml; do
  [ "$(basename "$f")" = "namespace.yaml" ] && continue
  docker compose exec -T k3s kubectl apply -f - < "$f"
done
# Restart platform pods to pick up freshly loaded images
docker compose exec -T k3s kubectl rollout restart deployment -n platform 2>/dev/null || true
echo "  Platform namespace ready."

# 7. Wait for application services
echo "[7/7] Waiting for application services..."
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
echo "  Web UI:      http://localhost:3000"
echo "  API Server:  http://localhost:8000"
echo "  API Health:  http://localhost:8000/api/health"
echo ""
echo "Infrastructure:"
echo "  PostgreSQL:  localhost:5432  (aviary/aviary)"
echo "  Redis:       localhost:6379"
echo "  Keycloak:    http://localhost:8080  (admin/admin)"
echo "  Vault:       http://localhost:8200  (token: dev-root-token)"
echo "  K3s API:     https://localhost:6443"
echo ""
echo "Test users (Keycloak):"
echo "  admin@test.com / password  (platform_admin, team: engineering)"
echo "  user1@test.com / password  (regular_user,   team: engineering, product)"
echo "  user2@test.com / password  (regular_user,   team: data-science)"
echo ""
echo "Hot reload:"
echo "  Edit files in api/ or web/ — changes apply automatically."
echo "  If you change dependencies (pyproject.toml / package.json):"
echo "    docker compose up -d --build api"
echo "    docker compose up -d --build web"
echo "  To rebuild K3s images:"
echo "    docker build -t aviary-runtime:latest ./runtime/"
echo "    docker build -t aviary-inference-router:latest ./inference-router/"
echo "    docker build -t aviary-egress-proxy:latest ./egress-proxy/"
echo "    docker save aviary-runtime:latest aviary-inference-router:latest aviary-egress-proxy:latest | docker compose exec -T k3s ctr images import -"
echo "    docker compose exec -T k3s kubectl rollout restart deployment -n platform"
