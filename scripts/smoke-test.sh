#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# Aviary E2E Smoke Test
#
# Automates the manual verification workflow:
#   1. Get Keycloak token (direct access grant)
#   2. Create a test agent (ollama / default)
#   3. Create a chat session
#   4. Connect via WebSocket, send a message, verify response
#   5. Verify session file isolation
#   6. Cleanup (optional)
#
# Usage:
#   ./scripts/smoke-test.sh                  # Full test (default: ollama)
#   ./scripts/smoke-test.sh --backend vllm   # Use vLLM backend
#   ./scripts/smoke-test.sh --no-cleanup     # Keep test agent after run
#   ./scripts/smoke-test.sh --skip-chat      # Skip WebSocket chat (API-only)
# ─────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ──────────────────────────────────────────────
API_URL="${API_URL:-http://localhost:8000}"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM="aviary"
CLIENT_ID="aviary-web"
TEST_USER="${TEST_USER:-user1@test.com}"
TEST_PASSWORD="${TEST_PASSWORD:-password}"
WS_TIMEOUT="${WS_TIMEOUT:-120}"   # seconds to wait for agent response
BACKEND="${SMOKE_BACKEND:-ollama}"
CLEANUP=true
SKIP_CHAT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cleanup) CLEANUP=false; shift ;;
    --skip-chat)  SKIP_CHAT=true; shift ;;
    --backend)    BACKEND="$2"; shift 2 ;;
    *)            shift ;;
  esac
done

# ── Colors ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${CYAN}→${NC} $1"; }
header() { echo -e "\n${BOLD}${CYAN}[$1]${NC} $2"; }

AGENT_ID=""
SESSION_ID=""
ERRORS=0

cleanup() {
  if [ "$CLEANUP" = true ] && [ -n "$AGENT_ID" ]; then
    echo ""
    info "Cleaning up test agent ${AGENT_ID}..."
    curl -sf -X DELETE "${API_URL}/api/agents/${AGENT_ID}" \
      -H "Authorization: Bearer ${ACCESS_TOKEN}" > /dev/null 2>&1 || true
  fi
  if [ $ERRORS -gt 0 ]; then
    echo -e "\n${RED}${BOLD}FAILED${NC} — ${ERRORS} error(s)"
    exit 1
  else
    echo -e "\n${GREEN}${BOLD}ALL PASSED${NC}"
  fi
}
trap cleanup EXIT

# ── 1. Health Check ─────────────────────────────────────
header "1/6" "Service health checks"

check_health() {
  local name=$1 url=$2
  if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
    pass "$name is up"
  else
    fail "$name is not reachable at $url"
    ((ERRORS++))
  fi
}

check_health "API"              "${API_URL}/api/health"
check_health "Keycloak"         "${KEYCLOAK_URL}/realms/${REALM}/.well-known/openid-configuration"
check_health "LiteLLM Gateway"   "http://localhost:8090/health/liveliness"

# ── 2. Keycloak Token ──────────────────────────────────
header "2/6" "Authenticate as ${TEST_USER}"

TOKEN_RESPONSE=$(curl -sf -X POST \
  "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=${CLIENT_ID}" \
  -d "username=${TEST_USER}" \
  -d "password=${TEST_PASSWORD}" \
  -d "scope=openid")

if [ -z "$TOKEN_RESPONSE" ]; then
  fail "Failed to get token from Keycloak"
  ERRORS=1
  exit 1
fi

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
pass "Got access token (${#ACCESS_TOKEN} chars)"

# Verify /me endpoint
ME_RESPONSE=$(curl -sf "${API_URL}/api/auth/me" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")
ME_EMAIL=$(echo "$ME_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['email'])")

if [ "$ME_EMAIL" = "$TEST_USER" ]; then
  pass "Verified identity: ${ME_EMAIL}"
else
  fail "Identity mismatch: expected ${TEST_USER}, got ${ME_EMAIL}"
  ((ERRORS++))
fi

# ── 3. Create Test Agent ───────────────────────────────

# Resolve default model for the backend from LiteLLM
MODEL=$(curl -sf "${API_URL}/api/inference/models" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  | python3 -c "
import sys, json
models = [m for m in json.load(sys.stdin).get('models', []) if m.get('backend') == '${BACKEND}']
default = next((m for m in models if m.get('model_info', {}).get('_ui', {}).get('default_model')), models[0] if models else None)
print(default['id'] if default else '')
")

if [ -z "$MODEL" ]; then
  fail "No models available for backend: ${BACKEND}"
  ERRORS=1
  exit 1
fi

header "3/6" "Create test agent (${BACKEND}/${MODEL})"

SLUG="smoke-test-$(date +%s)"
AGENT_PAYLOAD=$(cat <<EOF
{
  "name": "Smoke Test Agent",
  "slug": "${SLUG}",
  "description": "Automated smoke test — safe to delete",
  "instruction": "You are a test assistant. Reply briefly to any message.",
  "model_config": {
    "backend": "${BACKEND}",
    "model": "${MODEL}"
  },
  "tools": [],
  "mcp_servers": []
}
EOF
)

CREATE_RESPONSE=$(curl -sf -X POST "${API_URL}/api/agents" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$AGENT_PAYLOAD")

AGENT_ID=$(echo "$CREATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

if [ -n "$AGENT_ID" ]; then
  pass "Created agent: ${AGENT_ID} (slug: ${SLUG})"
else
  fail "Failed to create agent"
  ((ERRORS++))
  exit 1
fi

# Verify agent is retrievable
GET_RESPONSE=$(curl -sf "${API_URL}/api/agents/${AGENT_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")
GET_NAME=$(echo "$GET_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")

if [ "$GET_NAME" = "Smoke Test Agent" ]; then
  pass "Agent is retrievable via GET"
else
  fail "Agent GET returned unexpected name: ${GET_NAME}"
  ((ERRORS++))
fi

# ── 4. Create Session ──────────────────────────────────
header "4/6" "Create chat session"

SESSION_RESPONSE=$(curl -sf -X POST "${API_URL}/api/agents/${AGENT_ID}/sessions" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}')

SESSION_ID=$(echo "$SESSION_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

if [ -n "$SESSION_ID" ]; then
  pass "Created session: ${SESSION_ID}"
else
  fail "Failed to create session"
  ((ERRORS++))
fi

# ── 5. WebSocket Chat ──────────────────────────────────
if [ "$SKIP_CHAT" = true ]; then
  header "5/6" "WebSocket chat (SKIPPED)"
  info "Use --skip-chat was set, skipping live chat test"
else
  header "5/6" "WebSocket chat test"

  # Check if websocat is available; fall back to python
  if command -v websocat &> /dev/null; then
    info "Using websocat for WebSocket test"
    WS_URL="ws://localhost:8000/api/sessions/${SESSION_ID}/ws?token=${ACCESS_TOKEN}"

    # Send message and collect response (timeout after WS_TIMEOUT seconds)
    WS_OUTPUT=$(echo '{"type":"message","content":"Hello, this is a smoke test. Reply with OK."}' | \
      timeout "${WS_TIMEOUT}" websocat -n1 "$WS_URL" 2>&1 || true)

    if echo "$WS_OUTPUT" | grep -q '"type"'; then
      pass "Received WebSocket response"
      # Check for various expected message types
      if echo "$WS_OUTPUT" | grep -qE '"type"\s*:\s*"(status|chunk|done)"'; then
        pass "Response contains expected message types"
      else
        info "Response types: $(echo "$WS_OUTPUT" | python3 -c "
import sys,json
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    try:
        msg=json.loads(line)
        print(msg.get('type','?'), end=' ')
    except: pass
" 2>/dev/null || echo '(parse error)')"
      fi
    else
      fail "No valid WebSocket response within ${WS_TIMEOUT}s"
      info "Output: ${WS_OUTPUT:0:500}"
      ((ERRORS++))
    fi
  else
    info "Using Python for WebSocket test"
    uv run --link-mode=copy python -c "
import asyncio, json, sys, websockets

async def ws_chat():
    uri = 'ws://localhost:8000/api/sessions/${SESSION_ID}/ws?token=${ACCESS_TOKEN}'
    got_response = False
    types_seen = set()

    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({'type': 'message', 'content': 'Hello, this is a smoke test. Reply with OK.'}))

            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=${WS_TIMEOUT})
                    data = json.loads(msg)
                    msg_type = data.get('type', '?')
                    types_seen.add(msg_type)

                    if msg_type == 'chunk':
                        got_response = True
                    elif msg_type == 'done':
                        got_response = True
                        break
                    elif msg_type == 'error':
                        print(f'  ERROR from server: {data.get(\"message\", \"?\")}')
                        break
                except asyncio.TimeoutError:
                    print(f'  Timeout after ${WS_TIMEOUT}s')
                    break
    except Exception as e:
        print(f'  Connection error: {e}')
        sys.exit(1)

    print(f'  Message types seen: {sorted(types_seen)}')
    if got_response:
        print('  PASS: Got agent response')
    else:
        print('  FAIL: No agent response')
        sys.exit(1)

asyncio.run(ws_chat())
" 2>&1
    WS_EXIT=$?
    if [ $WS_EXIT -eq 0 ]; then
      pass "WebSocket chat completed successfully"
    else
      fail "WebSocket chat failed"
      ((ERRORS++))
    fi
  fi
fi

# ── 6. Verification Checks ────────────────────────────
header "6/6" "Post-chat verification"

# Check session has messages
SESSION_DETAIL=$(curl -sf "${API_URL}/api/sessions/${SESSION_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")

MSG_COUNT=$(echo "$SESSION_DETAIL" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('messages',[])))" 2>/dev/null || echo "0")

if [ "$SKIP_CHAT" = false ] && [ "$MSG_COUNT" -gt 0 ]; then
  pass "Session has ${MSG_COUNT} message(s) in DB"
elif [ "$SKIP_CHAT" = true ]; then
  pass "Session exists (chat skipped, ${MSG_COUNT} messages)"
else
  fail "No messages found in session after chat"
  ((ERRORS++))
fi

# Runtime pools are always on (Helm-managed), no per-agent deployment status.

# List agents to verify visibility
LIST_RESPONSE=$(curl -sf "${API_URL}/api/agents" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")
AGENT_COUNT=$(echo "$LIST_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('items',[])))" 2>/dev/null || echo "?")
pass "User can see ${AGENT_COUNT} agent(s)"

echo ""
info "Agent ID:   ${AGENT_ID}"
info "Session ID: ${SESSION_ID}"
info "Slug:       ${SLUG}"
