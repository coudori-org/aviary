# Aviary

Multi-tenant AI agent platform. Users create/configure agents via Web UI, each running in isolated K8s namespaces with long-running agent Pods powered by claude-agent-sdk.

## Quick Start

```bash
./scripts/setup-dev.sh   # First time: builds everything, loads K8s images
docker compose up -d      # Subsequent: just start services
```

Services: Web (`:3000`), API (`:8000`), Keycloak (`:8080`, admin/admin), Vault (`:8200`), Inference Router (`:8090`), Credential Proxy (`:8091`), Agent Controller (`:9000`).
Test accounts: `admin@test.com`, `user1@test.com`, `user2@test.com` (all `password`).

## Architecture

```
Browser → Next.js (:3000) → API rewrite proxy → FastAPI (:8000) → Agent Controller (:9000) → Agent Pods
                                                      ↓
                                               PostgreSQL / Redis / Vault / Keycloak

Platform services (docker compose):
  Inference Router (:8090) → Claude API / Ollama / vLLM / Bedrock
  Credential Proxy (:8091) → Vault

Platform services (K8s, platform namespace):
  Agent Controller (:9000, NodePort 30900) → K8s API (namespace/deployment/pod management)
  Egress Proxy → per-agent outbound policy enforcement

Agent Pod outbound:
  LLM calls  → Inference Router (host:8090) → Claude API / Ollama / vLLM / Bedrock
  Secrets    → Credential Proxy (host:8091) → Vault
  HTTP/HTTPS → Egress Proxy (K8s platform NS, per-agent policy) → External APIs
```

**Key flows:**
- Agent CRUD → API calls Agent Controller → creates K8s Namespace + ConfigMap + NetworkPolicy + ResourceQuota + ServiceAccount + syncs egress policy to Redis
- Chat message → WebSocket → ensure Deployment running (via Controller) → Controller SSE proxy to agent Pod → claude-agent-sdk → Inference Router → LLM backend
- Agent config edits → passed from DB on every message request body (NOT via ConfigMap). Immediate effect, no Pod restart.
- Egress policy edits → Redis update + NetworkPolicy PUT (via Controller) + egress-proxy cache invalidation (via Controller). Immediate effect, no Pod restart.

**Pod Strategy (agent-per-pod):** Each agent gets a long-running Deployment with 1-N replicas. Multiple sessions share the same Pod(s), isolated by working directory (`/workspace/sessions/{session_id}/`). Pods auto-scale based on session load and are released after 7 days of inactivity.

**Spawn strategies** (`pod_strategy` field):
- `lazy` (default): Deployment created on first chat message
- `eager`: Deployment created when agent is created
- `manual`: Admin must call `POST /agents/{id}/activate`

**Inference Router** (docker compose, `:8090`): All LLM calls go through a centralized proxy. Model name determines backend: `claude-*` → Claude API, `name:tag` → Ollama, `org/model` → vLLM, `anthropic.*` → Bedrock. Speaks Anthropic Messages API so claude-agent-sdk works transparently. API server also queries it for model listing (`/v1/backends/{backend}/models`).

**Credential Proxy** (docker compose, `:8091`): Session Pods never hold secrets. External API calls go through proxy which injects credentials from Vault.

**Agent Controller** (K8s platform namespace, `:9000`): All K8s operations are routed through this gateway service. The API server has no direct K8s dependency (no kubeconfig). The Controller runs inside K8s using in-cluster ServiceAccount auth, exposed externally via NodePort 30900. Handles: namespace/deployment/service/PVC CRUD, SSE streaming proxy to agent Pods, abort relay, egress proxy cache invalidation, deployment readiness polling, pod metrics for scaling. See `controller/` directory.

**Egress Proxy** (K8s platform namespace): All outbound HTTP/HTTPS from agent Pods is routed through a centralized forward proxy via `HTTP_PROXY`/`HTTPS_PROXY` env vars. Stays in K8s because it needs pod IP → namespace resolution for agent identification. Identifies source agent by resolving pod IP → K8s namespace → agent ID. Per-agent egress policies stored in Redis (`egress:{agent_id}`). Supports CIDR, exact domain, wildcard domain (`*.example.com`, `.example.com`), and catch-all (`*`). Deny-by-default. Admin API on port 8081 (`/health`, `/invalidate/{agent_id}`). CIDR rules are also enforced at NetworkPolicy level for non-HTTP traffic.

## Critical Patterns & Gotchas

### OIDC Dual-URL Pattern
Keycloak tokens have `iss=http://localhost:8080/...` (browser URL), but API container must fetch OIDC metadata from `http://keycloak:8080/...` (internal DNS). Two env vars: `OIDC_ISSUER` (public, for token validation) and `OIDC_INTERNAL_ISSUER` (internal, for discovery/JWKS/exchange). See `_rewrite_url()` / `to_public_url()` in `auth/oidc.py`.

### Pydantic v2 `model_config` Conflict
`model_config` is a reserved Pydantic class variable. Use `Field(alias="model_config")` with `model_config_data` as the Python field name. The `model_config = {...}` class var must be declared BEFORE field definitions. See `schemas/agent.py`.

### claude-agent-sdk Multi-Turn (TypeScript)
Uses the `query()` function from `@anthropic-ai/claude-agent-sdk` (TypeScript). TS SDK doesn't expose a `sessionId` option — Aviary session_id is injected via `extraArgs: { "session-id": sessionId }` which passes `--session-id <uuid>` to the CLI on the first message. Subsequent messages use `resume: sessionId` to load existing conversation history. Resume is determined by checking for existing JSONL in `<workspace>/.claude/projects/`. CLI session data is persisted to PVC via bwrap bind-mount of `<workspace>/.claude/` to `/tmp/.claude`, enabling conversation resume across Pod restarts. Runtime is a Node.js/Express server (`src/server.ts`) — no Python dependency. MCP servers from agent config are passed through to the SDK via `mcpServers` option. The runtime emits a final `result` SSE event with metadata (`total_cost_usd`, `usage`, `duration_ms`, `num_turns`) from the SDK's `ResultMessage` — the API can opt in to consuming this for billing/logging.

### Agent Controller for Pod Communication
API server communicates with K8s resources exclusively through the Agent Controller service (`controller/`). The Controller runs inside K8s (platform namespace) and uses in-cluster ServiceAccount RBAC for K8s API access. API calls Controller via HTTP (`AGENT_CONTROLLER_URL`). SSE streaming is transparently proxied: API → Controller → K8s Service proxy → Pod. See `controller_client.py` (API side) and `controller/app/routers/` (Controller side).

### Agent Deployment Lifecycle
`ensure_deployment()` in the Agent Controller creates Deployment + Service + PVC if not exists. The API calls this via `controller_client.ensure_deployment()`. The runtime Pod handles multiple sessions concurrently with per-session mutex locks and directory isolation. Idle agents (7 days) are scaled to 0, not deleted — re-activated on next message.

### Multi-Session Runtime
Each runtime Pod runs a `SessionManager` that tracks active sessions, enforces concurrency limits (`MAX_CONCURRENT_SESSIONS` env var, default 10), and serializes messages per-session. The readiness probe returns 503 when at capacity, preventing new session routing.

### Session Isolation (bubblewrap)
The `claude` binary in PATH is a wrapper script (`scripts/claude-sandbox.sh`). The real binary is renamed to `claude-real` at build time (see Dockerfile). SDK must use `pathToClaudeCodeExecutable: "/usr/local/bin/claude"` to bypass the bundled binary and use the wrapper. (node:22-slim puts npm global binaries in `/usr/local/bin/`, unlike the old python:3.12-slim + nodesource setup which used `/usr/bin/`.) When the SDK invokes `claude`, the wrapper reads `SESSION_WORKSPACE` from env (set per-session in `src/agent.ts`) and runs `claude-real` inside a bwrap mount namespace where `/workspace/sessions/` is an empty tmpfs with only the current session's directory bind-mounted back. `$SESSION_WORKSPACE/.claude` is bind-mounted to `/tmp/.claude` (HOME=/tmp) so CLI session data persists on PVC. Other sessions' files don't exist. PID namespace is also isolated.

### Auto-Scaling
Custom scaling loop in `scaling_service.py` (background task in API server, 30s interval). Queries pod metrics via Agent Controller (`GET /v1/pods/{ns}/metrics`). Scales up when sessions/pod > 5, down when < 2 (via Controller `PATCH /v1/deployments/{ns}/scale`). Clamped to `[min_pods, max_pods]` per agent.

### Egress Proxy Policy Enforcement
Two-layer enforcement: (1) K8s NetworkPolicy blocks all egress except DNS, platform NS (port 8080), and explicitly allowed CIDRs. (2) Egress proxy (HTTP-level) enforces domain-based rules. Agent pods have `HTTP_PROXY`/`HTTPS_PROXY` pointing to `egress-proxy.platform.svc:8080`, with `NO_PROXY` excluding internal platform services. Policy flow: API writes to Redis `egress:{agent_id}` key → calls Agent Controller `/v1/egress/invalidate/{agent_id}` → Controller relays to egress-proxy admin API → proxy re-reads from Redis on next request. See `redis_service.py:sync_egress_policy()`, `agent_service.py:update_agent()`, `egress-proxy/app/policy.py`.

### Egress Rule Schema
`EgressRule` in `schemas/agent.py` requires exactly one of `cidr` or `domain` (validated by `model_validator`). Domain patterns: `"example.com"` (exact), `"*.example.com"` (wildcard subdomain), `".example.com"` (same as `*`), `"*"` (all). Both types can be mixed in the same `allowedEgress` list. Optional `ports` field restricts to specific ports; empty means all ports allowed.

### Claude Code Managed Settings
`runtime/config/managed-settings.json` is installed to `/etc/claude-code/managed-settings.json` (the hardcoded path Claude Code CLI reads on Linux). Currently sets `skipWebFetchPreflight: true` to prevent CLI from calling `api.anthropic.com/api/web/domain_info` before each WebFetch — this endpoint is unreachable in air-gapped/fintech environments where all external traffic must go through the egress proxy. All model tiers (`ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, etc.) are remapped to the agent's configured model in `src/agent.ts` so that CLI internal tasks (WebFetch summarization, subagents) route through the inference router.

### K8s Image Loading
All K8s custom images use `imagePullPolicy: Never`. Loaded via `docker save | docker compose exec -T k8s ctr images import -`. The `setup-dev.sh` handles this for runtime, egress-proxy, and agent-controller images. Inference router and credential proxy run outside K8s and don't need image loading.

### K8s Fixed Node Name
`--node-name=aviary-node` in docker-compose.yml prevents stale node accumulation on container restart. Without it, PVCs bind to old node names causing scheduling failures.

### PVC Strategy
Single `agent-workspace` PVC (5Gi) per agent, shared by all replicas. Session data at `/workspace/sessions/{session_id}/`. `ReadWriteOnce` works for single-node; multi-node requires `ReadWriteMany` or StatefulSet migration.

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

## Rebuilding Images

**K8s images** (runtime, egress-proxy, agent-controller) — after modifying `runtime/`, `egress-proxy/`, or `controller/`:

```bash
docker build -t aviary-runtime:latest ./runtime/
docker build -t aviary-agent-controller:latest ./controller/
docker save aviary-runtime:latest aviary-agent-controller:latest | docker compose exec -T k8s ctr images import -
# Repeat pattern for egress-proxy if changed
```

**Docker Compose services** (inference-router, credential-proxy) — hot reload via bind-mount, or rebuild:

```bash
docker compose up -d --build inference-router credential-proxy
```

## Key Environment Variables (API)

| Variable | Purpose |
|----------|---------|
| `OIDC_ISSUER` | Public Keycloak URL (token `iss` validation) |
| `OIDC_INTERNAL_ISSUER` | Internal Keycloak URL (discovery/JWKS fetch) |
| `DATABASE_URL` | PostgreSQL async connection |
| `REDIS_URL` | Redis for pub/sub, caching, presence |
| `VAULT_ADDR` / `VAULT_TOKEN` | Vault connection |
| `AGENT_CONTROLLER_URL` | Agent Controller URL (default: `http://localhost:9000`) |
| `AGENT_RUNTIME_IMAGE` | Container image for agent Pods |
| `INFERENCE_ROUTER_URL` | Inference router URL (default: `http://inference-router:8080`) |
| `CREDENTIAL_PROXY_URL` | Credential proxy URL (default: `http://credential-proxy:8080`) |
| `DEFAULT_AGENT_IDLE_TIMEOUT` | Agent idle timeout in seconds (default: 604800 = 7 days) |
| `SCALING_CHECK_INTERVAL` | Auto-scaling check interval in seconds (default: 30) |

## Key Environment Variables (Runtime Pod)

| Variable | Purpose |
|----------|---------|
| `AGENT_ID` | Agent UUID |
| `MAX_CONCURRENT_SESSIONS` | Max sessions per pod (default: 10) |
| `CREDENTIAL_PROXY_URL` | Credential proxy URL (`http://credential-proxy.platform.svc:8080`) |
| `INFERENCE_ROUTER_URL` | Inference router URL (`http://inference-router.platform.svc:8080`) |
| `HTTP_PROXY` / `HTTPS_PROXY` | Egress proxy URL (`http://egress-proxy.platform.svc:8080`) |
| `NO_PROXY` | Bypass proxy for internal services (platform SVCs, localhost) |

## Key Environment Variables (Agent Controller)

| Variable | Purpose |
|----------|---------|
| `AGENT_RUNTIME_IMAGE` | Container image for agent Pods (default: `aviary-runtime:latest`) |
| `HOST_GATEWAY_IP` | Host IP for Pod hostAliases (injected by setup script) |
| `MAX_CONCURRENT_SESSIONS_PER_POD` | Max sessions per pod (default: 10) |

## Key Environment Variables (Egress Proxy)

| Variable | Purpose |
|----------|---------|
| `PROXY_PORT` | Forward proxy listen port (default: 8080) |
| `ADMIN_PORT` | Admin API listen port (default: 8081) |
| `REDIS_URL` | Redis for per-agent egress policies |
