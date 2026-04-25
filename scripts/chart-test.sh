#!/usr/bin/env bash
# Helm chart validation — start K3s, build runtime images, apply charts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

load_env_and_build_args

echo "[1/5] Starting K3s..."
local_infra_compose --profile k3s up -d k8s

echo "[2/5] Waiting for K3s..."
until local_infra_compose --profile k3s exec -T k8s kubectl get nodes 2>/dev/null | grep -q " Ready"; do
  sleep 2
done
K8S_GATEWAY_IP=$(k8s_gateway_ip)
echo "  K3s gateway IP: $K8S_GATEWAY_IP"

echo "[3/5] Building runtime images..."
docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} -t aviary-runtime:latest "$PROJECT_DIR/runtime/"
load_k8s_image aviary-runtime:latest
docker build ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} -f "$PROJECT_DIR/runtime/Dockerfile.custom" -t aviary-runtime-custom:latest "$PROJECT_DIR/runtime/"
load_k8s_image aviary-runtime-custom:latest

echo "[4/5] Rendering and applying Helm charts..."
HELM_IMAGE="alpine/helm:3.14.4"

render_chart() {
  local release=$1 chart=$2 values=$3
  docker run --rm -v "$CHARTS_DIR:/charts:ro" "$HELM_IMAGE" template \
    "$release" "/charts/$chart" -f "/charts/$chart/$values" \
    --set hostGatewayIP="$K8S_GATEWAY_IP"
}

render_chart aviary-platform    aviary-platform    values-dev.yaml \
  | local_infra_compose --profile k3s exec -T k8s kubectl apply -f -
render_chart aviary-env-default aviary-environment values-dev.yaml \
  | local_infra_compose --profile k3s exec -T k8s kubectl apply -f -
render_chart aviary-env-custom  aviary-environment values-custom.yaml \
  | local_infra_compose --profile k3s exec -T k8s kubectl apply -f -

echo "[5/5] Waiting for runtime rollouts..."
echo -n "  default..."
local_infra_compose --profile k3s exec -T k8s kubectl -n agents rollout status deploy/aviary-env-default --timeout=180s
echo " ready."
echo -n "  custom..."
local_infra_compose --profile k3s exec -T k8s kubectl -n agents rollout status deploy/aviary-env-custom --timeout=180s
echo " ready."

cat <<EOF

NodePorts:
  aviary-env-default: http://localhost:30300
  aviary-env-custom:  http://localhost:30301

Route supervisor through K3s by setting in .env:
  SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT=http://host.docker.internal:30300
Then: docker compose up -d supervisor

Iterate on runtime code: ./scripts/quick-rebuild.sh runtime
EOF
