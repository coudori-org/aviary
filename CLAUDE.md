# Aviary

Multi-tenant AI agent platform. Users create/configure agents via Web UI, each running in isolated K8s namespaces with long-running agent Pods powered by claude-agent-sdk.

## Quick Start

```bash
./scripts/setup-dev.sh   # First time: builds everything, loads K3s images
docker compose up -d      # Subsequent: just start services
```

Services: Web (`:3000`), API (`:8000`), Keycloak (`:8080`, admin/admin), Vault (`:8200`).
Test accounts: `admin@test.com`, `user1@test.com`, `user2@test.com` (all `password`).

## Architecture

```
Browser → Next.js (:3000) → API rewrite proxy → FastAPI (:8000) → K8s Service → Agent Pods
                                                      ↓
                                               PostgreSQL / Redis / Vault / Keycloak
```

**Key flows:**
- Agent CRUD → creates K8s Namespace + ConfigMap + NetworkPolicy + ResourceQuota + ServiceAccount
- Chat message → WebSocket → ensure Deployment running → K8s API proxy to Service → agent Pod → claude-agent-sdk → Inference Router → LLM backend
- Agent config edits → passed from DB on every message request body (NOT via ConfigMap). Immediate effect, no Pod restart.

**Pod Strategy (agent-per-pod):** Each agent gets a long-running Deployment with 1-N replicas. Multiple sessions share the same Pod(s), isolated by working directory (`/workspace/sessions/{session_id}/`). Pods auto-scale based on session load and are released after 7 days of inactivity.

**Spawn strategies** (`pod_strategy` field):
- `lazy` (default): Deployment created on first chat message
- `eager`: Deployment created when agent is created
- `manual`: Admin must call `POST /agents/{id}/activate`

**Inference Router** (platform namespace): All LLM calls go through a centralized proxy. Model name determines backend: `claude-*` → Claude API, `name:tag` → Ollama, `org/model` → vLLM, `anthropic.*` → Bedrock. Speaks Anthropic Messages API so claude-agent-sdk works transparently.

**Credential Proxy** (platform namespace): Session Pods never hold secrets. External API calls go through proxy which injects credentials from Vault.

## Critical Patterns & Gotchas

### OIDC Dual-URL Pattern
Keycloak tokens have `iss=http://localhost:8080/...` (browser URL), but API container must fetch OIDC metadata from `http://keycloak:8080/...` (internal DNS). Two env vars: `OIDC_ISSUER` (public, for token validation) and `OIDC_INTERNAL_ISSUER` (internal, for discovery/JWKS/exchange). See `_rewrite_url()` / `to_public_url()` in `auth/oidc.py`.

### Pydantic v2 `model_config` Conflict
`model_config` is a reserved Pydantic class variable. Use `Field(alias="model_config")` with `model_config_data` as the Python field name. The `model_config = {...}` class var must be declared BEFORE field definitions. See `schemas/agent.py`.

### claude-agent-sdk Multi-Turn
Uses `resume=<session_id>` (NOT `continue_conversation + session_id`). Session ID stored at `/workspace/sessions/{session_id}/.session_id` on PVC, survives Pod restarts. Each session has its own workspace directory within the shared PVC.

### K8s Service Proxy for Pod Communication
API container is outside K3s network. Communicates with agent Pods via K8s Service proxy: `POST /api/v1/namespaces/{ns}/services/agent-runtime-svc:3000/proxy/message`. K8s load-balances across replicas. See `stream_manager.py` and `deployment_service.py`.

### Agent Deployment Lifecycle
`ensure_agent_deployment()` in `deployment_service.py` creates Deployment + Service + PVC if not exists. The runtime Pod handles multiple sessions concurrently with per-session asyncio locks and directory isolation. Idle agents (7 days) are scaled to 0, not deleted — re-activated on next message.

### Multi-Session Runtime
Each runtime Pod runs a `SessionManager` that tracks active sessions, enforces concurrency limits (`MAX_CONCURRENT_SESSIONS` env var, default 10), and serializes messages per-session. The readiness probe returns 503 when at capacity, preventing new session routing.

### Session Isolation (bubblewrap)
The `claude` binary in PATH is a wrapper script (`scripts/claude-sandbox.sh`). The real binary is renamed to `claude-real` at build time (see Dockerfile). When the SDK invokes `claude`, the wrapper reads `SESSION_WORKSPACE` from env (set per-session in `agent.py`) and runs `claude-real` inside a bwrap mount namespace where `/workspace/sessions/` is an empty tmpfs with only the current session's directory bind-mounted back. Other sessions' files don't exist. PID namespace is also isolated.

### Auto-Scaling
Custom scaling loop in `scaling_service.py` (background task, 30s interval). Queries each Pod's `GET /metrics` endpoint for session counts. Scales up when sessions/pod > 5, down when < 2. Clamped to `[min_pods, max_pods]` per agent.

### K3s Image Loading
All custom images use `imagePullPolicy: Never`. Loaded via `docker save | docker compose exec -T k3s ctr images import -`. The `setup-dev.sh` handles this for runtime, inference-router, and credential-proxy images.

### K3s Fixed Node Name
`--node-name=aviary-node` in docker-compose.yml prevents stale node accumulation on container restart. Without it, PVCs bind to old node names causing scheduling failures.

### PVC Strategy
Single `agent-workspace` PVC (5Gi) per agent, shared by all replicas. Session data at `/workspace/sessions/{session_id}/`. `ReadWriteOnce` works for K3s single-node; multi-node requires `ReadWriteMany` or StatefulSet migration.

### React Strict Mode
Use `useRef` guards for WebSocket connections and OIDC callbacks to prevent duplicate execution in dev mode.

### Team Sync
Teams auto-synced from Keycloak/Okta `groups` claim on every login via `team_sync_service.py`. No manual team management.

## ACL Resolution (7 steps)

1. Platform admin → full access
2. Agent owner → full access
3. Direct user ACL entry
4. Team ACL entries (highest role wins)
5. `visibility=public` → implicit `user` role
6. `visibility=team` → implicit `user` role if shared team with owner
7. Deny

Role hierarchy: `viewer` < `user` < `admin` < `owner`.

## Testing

```bash
docker compose exec api pytest tests/ -v
```

16 tests using dedicated `aviary_test` database with `NullPool` (avoids asyncpg conflicts). Test app has no lifespan (no background tasks). Mock auth via `_TOKEN_CLAIMS` dict mapping tokens to claims for multi-user scenarios.

## Rebuilding K8s Images

After modifying `runtime/`, `inference-router/`, or `credential-proxy/`:

```bash
docker build -t aviary-runtime:latest ./runtime/
docker save aviary-runtime:latest | docker compose exec -T k3s ctr images import -
# Repeat for inference-router and credential-proxy if changed
```

## Key Environment Variables (API)

| Variable | Purpose |
|----------|---------|
| `OIDC_ISSUER` | Public Keycloak URL (token `iss` validation) |
| `OIDC_INTERNAL_ISSUER` | Internal Keycloak URL (discovery/JWKS fetch) |
| `DATABASE_URL` | PostgreSQL async connection |
| `REDIS_URL` | Redis for pub/sub, caching, presence |
| `VAULT_ADDR` / `VAULT_TOKEN` | Vault connection |
| `KUBECONFIG` | K3s kubeconfig path |
| `AGENT_RUNTIME_IMAGE` | Container image for agent Pods |
| `HOST_GATEWAY_IP` | Host IP for K3s Pods to reach Ollama/vLLM on host |
| `DEFAULT_AGENT_IDLE_TIMEOUT` | Agent idle timeout in seconds (default: 604800 = 7 days) |
| `SCALING_CHECK_INTERVAL` | Auto-scaling check interval in seconds (default: 30) |

## Key Environment Variables (Runtime Pod)

| Variable | Purpose |
|----------|---------|
| `AGENT_ID` | Agent UUID |
| `MAX_CONCURRENT_SESSIONS` | Max sessions per pod (default: 10) |
| `CREDENTIAL_PROXY_URL` | Credential proxy service URL |
| `INFERENCE_OLLAMA_URL` | Ollama inference URL |
| `INFERENCE_VLLM_URL` | vLLM inference URL |
