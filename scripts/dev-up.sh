#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "$SCRIPT_DIR/_common.sh"

load_env_and_build_args

echo "[1/4] Starting local-infra..."
local_infra_compose up -d

echo "[2/4] Waiting for local-infra readiness..."
echo -n "  PostgreSQL..."
until local_infra_compose exec -T postgres pg_isready -U aviary > /dev/null 2>&1; do sleep 1; done
echo " ready."
echo -n "  Keycloak..."
until curl -sf http://localhost:8080/realms/aviary/.well-known/openid-configuration > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  LiteLLM..."
until curl -sf http://localhost:8090/health/liveliness > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  Temporal..."
until curl -sf http://localhost:8233 > /dev/null 2>&1; do sleep 2; done
echo " ready."

echo "[3/4] Building and starting services..."
services_compose up -d --build

echo "[4/4] Waiting for service readiness..."
echo -n "  Agent Supervisor..."
until curl -sf http://localhost:9000/v1/health > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  API server..."
until curl -sf http://localhost:8000/api/health > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  Admin console..."
until curl -sf http://localhost:8001/ > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  Web UI..."
until curl -sf http://localhost:3000 > /dev/null 2>&1; do sleep 2; done
echo " ready."

cat <<'EOF'

=== Dev environment is ready! ===

  Web UI:             http://localhost:3000
  API Server:         http://localhost:8000   (health: /api/health)
  Admin Console:      http://localhost:8001
  Agent Supervisor:   http://localhost:9000   (metrics: /metrics)
  LiteLLM Gateway:    http://localhost:8090   (inference + /mcp)
  Temporal UI:        http://localhost:8233   (gRPC: localhost:7233)
  PostgreSQL:         localhost:5432  (aviary/aviary)
  Redis:              localhost:6379
  Keycloak:           http://localhost:8080   (admin/admin)
  Vault:              http://localhost:8200   (token: dev-root-token)
  Prometheus:         http://localhost:9090
  Grafana:            http://localhost:3001

Test users: user1@test.com / user2@test.com (password: password)

Helm chart validation:  ./scripts/chart-test.sh
Tear down:              ./scripts/dev-down.sh
EOF
