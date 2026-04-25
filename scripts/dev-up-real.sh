#!/usr/bin/env bash
# Built mode: services from baked images, no bind-mounts, no --reload.
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

echo "[3/4] Building and starting services (no override)..."
(cd "$PROJECT_DIR" && docker compose -f compose.yml up -d --build)

echo "[4/4] Waiting for service readiness..."
echo -n "  Supervisor..."
until curl -sf http://localhost:9000/v1/health > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  API..."
until curl -sf http://localhost:8000/api/health > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  Admin..."
until curl -sf http://localhost:8001/ > /dev/null 2>&1; do sleep 2; done
echo " ready."
echo -n "  Web..."
until curl -sf http://localhost:3000 > /dev/null 2>&1; do sleep 2; done
echo " ready."

cat <<'EOF'

Web:        http://localhost:3000
API:        http://localhost:8000
Admin:      http://localhost:8001
Supervisor: http://localhost:9000

Rebuild:    ./scripts/quick-rebuild.sh real
Back to dev: ./scripts/dev-down.sh && ./scripts/dev-up.sh
EOF
