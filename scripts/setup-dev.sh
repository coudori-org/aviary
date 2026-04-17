#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=== Aviary Dev Environment Setup ==="

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_DIR/.env"
  set +a
fi

BUILD_ARGS=()
[ -n "${UV_INDEX_URL:-}" ]        && BUILD_ARGS+=(--build-arg "UV_INDEX_URL=$UV_INDEX_URL")
[ -n "${NPM_CONFIG_REGISTRY:-}" ] && BUILD_ARGS+=(--build-arg "NPM_CONFIG_REGISTRY=$NPM_CONFIG_REGISTRY")

echo "[1/6] Building and starting Docker Compose services..."
docker compose up -d --build

echo "[2/6] Waiting for PostgreSQL..."
until docker compose exec -T postgres pg_isready -U aviary > /dev/null 2>&1; do
  sleep 1
done
echo "  PostgreSQL is ready."

echo "[3/6] Waiting for Keycloak..."
until curl -sf http://localhost:8080/realms/aviary/.well-known/openid-configuration > /dev/null 2>&1; do
  sleep 2
done
echo "  Keycloak is ready."

echo "[4/6] Waiting for K8s..."
until docker compose exec -T k8s kubectl get nodes 2>/dev/null | grep -q " Ready"; do
  sleep 2
done
echo "  K8s is ready."

K8S_GATEWAY_IP=$(docker compose exec -T k8s ip route | awk '/default/ {print $3}' | head -1)
echo "  K8s gateway IP: $K8S_GATEWAY_IP"

# Only runtime images live in K3s now. Supervisor runs as a compose service.
echo "[5/6] Building and loading runtime images..."
docker build "${BUILD_ARGS[@]}" -t aviary-runtime:latest ./runtime/
docker save aviary-runtime:latest | docker compose exec -T k8s ctr images import -
# Example customized variant (used by the `custom` environment) — extends the base.
docker build "${BUILD_ARGS[@]}" -f ./runtime/Dockerfile.custom -t aviary-runtime-custom:latest ./runtime/
docker save aviary-runtime-custom:latest | docker compose exec -T k8s ctr images import -

echo "  Rendering and applying Helm charts..."
HELM_IMAGE="alpine/helm:3.14.4"

render_chart() {
  local release=$1 chart=$2 values=$3
  docker run --rm -v "$PROJECT_DIR/charts:/charts:ro" "$HELM_IMAGE" template \
    "$release" "/charts/$chart" -f "/charts/$chart/$values" \
    --set hostGatewayIP="$K8S_GATEWAY_IP"
}

render_chart aviary-platform    aviary-platform    values-dev.yaml \
  | docker compose exec -T k8s kubectl apply -f -
render_chart aviary-env-default aviary-environment values-dev.yaml \
  | docker compose exec -T k8s kubectl apply -f -
render_chart aviary-env-custom  aviary-environment values-custom.yaml \
  | docker compose exec -T k8s kubectl apply -f -

echo "  Platform + default + custom environments applied."

echo -n "  Waiting for default runtime rollout..."
docker compose exec -T k8s kubectl -n agents rollout status deploy/aviary-env-default --timeout=180s
echo " ready."
echo -n "  Waiting for custom runtime rollout..."
docker compose exec -T k8s kubectl -n agents rollout status deploy/aviary-env-custom --timeout=180s
echo " ready."

echo "[6/6] Waiting for application services..."
echo -n "  Temporal server..."
until curl -sf http://localhost:8233 > /dev/null 2>&1; do
  sleep 2
done
echo " ready."
echo -n "  Agent supervisor..."
until curl -sf http://localhost:9000/v1/health > /dev/null 2>&1; do
  sleep 2
done
echo " ready."
echo -n "  LiteLLM gateway..."
until curl -sf http://localhost:8090/health/liveliness > /dev/null 2>&1; do
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
echo "  Web UI:             http://localhost:3000"
echo "  API Server:         http://localhost:8000"
echo "  API Health:         http://localhost:8000/api/health"
echo ""
echo "Platform Services (docker compose):"
echo "  Agent Supervisor:   http://localhost:9000"
echo "  Supervisor metrics: http://localhost:9000/metrics"
echo "  LiteLLM Gateway:    http://localhost:8090"
echo "  MCP Gateway:        http://localhost:8100"
echo "  Temporal UI:        http://localhost:8233"
echo "  Temporal gRPC:      localhost:7233"
echo ""
echo "Runtime (K3s, Helm-managed):"
echo "  Default environment (egress locked down, base image):  NodePort :30300"
echo "  Custom  environment (open egress, example layered img): NodePort :30301"
echo "    Agent routing: set agent.runtime_endpoint = http://k8s:30301 via admin."
echo ""
echo "Infrastructure:"
echo "  PostgreSQL:  localhost:5432  (aviary/aviary)"
echo "  Redis:       localhost:6379"
echo "  Keycloak:    http://localhost:8080  (admin/admin)"
echo "  Vault:       http://localhost:8200  (token: dev-root-token)"
echo "  K8s API:     https://localhost:6443"
echo ""
echo "Test users (Keycloak):"
echo "  admin@test.com / password"
echo "  user1@test.com / password"
echo "  user2@test.com / password"
echo ""
echo "Hot reload:"
echo "  Edit files in api/, web/, admin/, agent-supervisor/ — changes via bind-mount."
echo "  Runtime image:     ./scripts/quick-rebuild.sh runtime"
echo "  Chart changes:     re-run setup-dev.sh (idempotent) or render+apply manually"
