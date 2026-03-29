# Aviary

Multi-tenant AI agent platform. Users create/configure agents via Web UI, each running in isolated K8s namespaces with per-session Pods powered by claude-agent-sdk.

## Quick Start

```bash
./scripts/setup-dev.sh   # First time: builds everything, loads K3s images
docker compose up -d      # Subsequent: just start services
```

Services: Web (`:3000`), API (`:8000`), Keycloak (`:8080`, admin/admin), Vault (`:8200`).
Test accounts: `admin@test.com`, `user1@test.com`, `user2@test.com` (all `password`).

## Architecture

```
Browser → Next.js (:3000) → API rewrite proxy → FastAPI (:8000) → K8s API → Session Pods
                                                      ↓
                                               PostgreSQL / Redis / Vault / Keycloak
```

**Key flows:**
- Agent CRUD → creates K8s Namespace + ConfigMap + NetworkPolicy + ResourceQuota + ServiceAccount
- Chat message → WebSocket → ensure Pod running → K8s API proxy to Pod → claude-agent-sdk → Inference Router → LLM backend
- Agent config edits → passed from DB on every message request body (NOT via ConfigMap). Immediate effect, no Pod restart.

**Inference Router** (platform namespace): All LLM calls go through a centralized proxy. Model name determines backend: `claude-*` → Claude API, `name:tag` → Ollama, `org/model` → vLLM, `anthropic.*` → Bedrock. Speaks Anthropic Messages API so claude-agent-sdk works transparently.

**Credential Proxy** (platform namespace): Session Pods never hold secrets. External API calls go through proxy which injects credentials from Vault.

## Critical Patterns & Gotchas

### OIDC Dual-URL Pattern
Keycloak tokens have `iss=http://localhost:8080/...` (browser URL), but API container must fetch OIDC metadata from `http://keycloak:8080/...` (internal DNS). Two env vars: `OIDC_ISSUER` (public, for token validation) and `OIDC_INTERNAL_ISSUER` (internal, for discovery/JWKS/exchange). See `_rewrite_url()` / `to_public_url()` in `auth/oidc.py`.

### Pydantic v2 `model_config` Conflict
`model_config` is a reserved Pydantic class variable. Use `Field(alias="model_config")` with `model_config_data` as the Python field name. The `model_config = {...}` class var must be declared BEFORE field definitions. See `schemas/agent.py`.

### claude-agent-sdk Multi-Turn
Uses `resume=<session_id>` (NOT `continue_conversation + session_id`). Session ID stored at `/workspace/.session_id` on PVC, survives Pod restarts.

### K8s API Proxy for Pod Communication
API container is outside K3s network. Communicates with session Pods via: `POST /api/v1/namespaces/{ns}/pods/{pod}:3000/proxy/message`. See `routers/sessions.py`.

### Session Pod Self-Healing
`ensure_session_pod()` in `session_service.py` checks if recorded Pod actually exists (including Terminating and stuck-Pending detection). Stale references auto-cleaned, new Pod spawned. Only Pod is deleted on cleanup — PVC preserved for workspace files and SDK session data.

### K3s Image Loading
All custom images use `imagePullPolicy: Never`. Loaded via `docker save | docker compose exec -T k3s ctr images import -`. The `setup-dev.sh` handles this for runtime, inference-router, and credential-proxy images.

### K3s Fixed Node Name
`--node-name=aviary-node` in docker-compose.yml prevents stale node accumulation on container restart. Without it, PVCs bind to old node names causing scheduling failures.

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
| `AGENT_RUNTIME_IMAGE` | Container image for session Pods |
| `HOST_GATEWAY_IP` | Host IP for K3s Pods to reach Ollama/vLLM on host |
