# Aviary

Multi-tenant AI agent platform. Users create/configure agents via Web UI; every agent runs in a **shared runtime environment** (a pre-provisioned K8s Deployment pool) powered by claude-agent-sdk.

## Quick Start

```bash
./scripts/setup-dev.sh   # First time: builds everything, installs Helm charts, loads K8s images
docker compose up -d      # Subsequent: just start services
```

Services: Web (`:3000`), API (`:8000`), Admin (`:8001`), Keycloak (`:8080`, admin/admin), Vault (`:8200`), LiteLLM Gateway (`:8090`), MCP Gateway (`:8100`), Agent Supervisor (`:9000`).
Test accounts: `user1@test.com`, `user2@test.com` (all `password`).

## Architecture

```
Browser → Next.js (:3000) → API rewrite proxy → FastAPI (:8000)
                                                  │
                                                  ├── Redis pub/sub (WS broadcast)
                                                  │
   WebSocket ◄────────── Redis subscribe ─────────┘
                                                  ▼
                      lookup agent.runtime_endpoint
                                                  │
                                                  ▼
                Agent Supervisor (:9000, stateless)
                      ├── SSE proxy → runtime pool
                      ├── publish every event to Redis
                      ├── assemble final message
                      └── /metrics (Prometheus)

Admin Console (:8001) → DB (no infra calls)

Platform (docker compose — same deploy unit as api/admin):
  Postgres, Redis, Keycloak, Vault, LiteLLM (:8090), MCP Gateway (:8100),
  **Agent Supervisor (:9000)**, API, Admin, Web

K8s cluster (Helm-managed; the only thing in K3s/EKS):
  charts/aviary-platform — namespaces, baseline egress NP,
    external-services proxy Services (dev only), image-warmer DaemonSet (optional)
  charts/aviary-environment — one release per runtime environment:
    Deployment (replicas fixed, min 1) — pool serves every agent
    Service (NodePort in dev → supervisor hits k8s:<port>; ClusterIP in prod)
    PVC (RWX — hostPath in dev / EFS in prod)
    optional per-env NetworkPolicy (union with baseline)

Agent routing:
  agent.runtime_endpoint (nullable) in the DB.
  null → supervisor's SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT (default env).
  non-null → any env Service DNS (admin sets per agent).
```

### Service Responsibilities

Three backend services with distinct roles:

**API Server (`:8000`)** — User-facing. Agent CRUD (config only), OIDC auth, ACL, sessions, chat. Looks up `agent.runtime_endpoint` and forwards it as part of each publish request body. No K8s concepts anywhere in `api/`.

**Admin Console (`:8001`)** — Operator-facing. No authentication (local-only). Manages agent config, including the optional `runtime_endpoint` override, plus MCP registration, ACL, users, and Vault credentials. Never talks to K8s or the supervisor — runtime infrastructure is Helm-managed.

**Agent Supervisor (`:9000`, docker compose service)** — Reverse SSE Proxy. Runs outside K8s, same deploy unit as API/Admin. No DB, no K8s API. Holds an **in-memory registry** of active publish tasks keyed by `(session_id, agent_id)`. Receives a publish request (body includes optional `runtime_endpoint` + agent_config), streams SSE from the runtime's Service endpoint, publishes every event to Redis (chunks + pub/sub), assembles the final text + blocks_meta, returns it to the caller. Emits Prometheus metrics at `/metrics`. **Abort** = lookup in the registry and `task.cancel()` — no HTTP forward to runtime needed; closing the outbound httpx stream propagates close through the Service-pinned TCP connection, which fires `req.on("close")` in the runtime pod and aborts the SDK.

**Shared DB package** (`shared/aviary_shared/`) — SQLAlchemy models, migrations, and session factory used by API + Admin. Migrations live at `shared/aviary_shared/db/migrations/` with alembic config at `shared/alembic.ini`.

**Key flows:**
- Agent creation → API saves config to DB. No infrastructure side effects.
- Agent routing edit → Admin updates `agent.runtime_endpoint` in DB. Effective on the next chat message.
- Chat message → WebSocket → API looks up `agent.runtime_endpoint` → `POST supervisor /v1/sessions/{sid}/publish` with body including `runtime_endpoint` and `agent_config` → supervisor streams SSE from `{endpoint}/message`, publishes each event to Redis, assembles final message and returns it → API saves the returned message to DB and publishes the `done` event. WS clients receive live events via independent Redis subscription.
- Agent config edit (instruction, tools, MCP servers) → API updates DB only. Passed to runtime on every message request body.

**Pod Strategy (env-per-pool, (agent, session)-per-workdir):** One Helm release per environment. Replicas fixed (min 1), no scale-to-zero. Every pod serves every agent. Isolation comes from per-(agent, session) on-disk paths plus bubblewrap — the pod itself is agent-agnostic.

**LiteLLM Gateway** (docker compose, `:8090`): All LLM calls go through LiteLLM OSS proxy. Backend is determined by the model name prefix (e.g., `anthropic/claude-sonnet-4-6` → Claude API, `ollama/gemma4:26b` → Ollama, `vllm/...` → vLLM, `bedrock/...` → Bedrock). Natively compatible with Anthropic SDK (`/v1/messages`), so claude-agent-sdk works transparently. Configuration in `config/litellm/config.yaml`. API server queries it for model listing (`/model/info`). Supports virtual keys, rate limiting, and per-user API key injection. Two startup patches loaded via `.pth` file: `fix_adapter_streaming.py` fixes Anthropic-to-OpenAI adapter streaming for non-Anthropic backends; `aviary_user_api_key.py` injects per-user Anthropic API keys from Vault.

**Agent Supervisor routes** (all session-centric, caller injects `runtime_endpoint`):
- `POST /v1/sessions/{sid}/message` — transparent SSE passthrough (used by the workflow engine).
- `POST /v1/sessions/{sid}/a2a` — sub-agent stream invoked directly by a parent runtime's local A2A MCP server. Body carries `target_agent_id` + `target_runtime_endpoint` (already ACL-filtered by the API at chat-start). Forwards SSE to the caller and tags `tool_use`/`tool_result` events into the parent session's Redis A2A buffer for assembly.
- `POST /v1/sessions/{sid}/publish` — SSE + Redis + assembly. Returns `{status, reached_runtime, assembled_text, assembled_blocks}`.
- `POST /v1/sessions/{sid}/abort` — best-effort abort on the runtime.
- `DELETE /v1/sessions/{sid}` — cleanup workspace directories for a given agent/session.
- `GET /v1/health`
- `GET /metrics` — Prometheus text format.

No background loops. No per-agent state. No 0↔1 activation — environments are always on.

**Egress policy** is set per environment via Helm:
- **Baseline** (`charts/aviary-platform/templates/default-egress.yaml`): namespace-wide `NetworkPolicy` on `aviary/role=agent-runtime`; allows DNS + platform NS + gateway ports (LiteLLM 8090, MCP 8100, API 8000, Supervisor 9000 — for A2A). Always in effect.
- **Per-environment extras**: optional `extraEgress` list in `charts/aviary-environment/values.yaml` gets merged into a second NetworkPolicy scoped by `aviary/environment=<name>`. K8s NP evaluates as a disjunction — this unions with baseline.

## Critical Patterns & Gotchas

### OIDC Dual-URL Pattern
Keycloak tokens have `iss=http://localhost:8080/...` (browser URL), but API container must fetch OIDC metadata from `http://keycloak:8080/...` (internal DNS). Two env vars: `OIDC_ISSUER` (public, for token validation) and `OIDC_INTERNAL_ISSUER` (internal, for discovery/JWKS/exchange). See `_rewrite_url()` / `to_public_url()` in `auth/oidc.py`.

### Pydantic v2 `model_config` Conflict
`model_config` is a reserved Pydantic class variable. Use `Field(alias="model_config")` with `model_config_data` as the Python field name. The `model_config = {...}` class var must be declared BEFORE field definitions. See `api/app/schemas/agent.py`.

### API + Admin Know Nothing About Infrastructure
Neither service has K8s concepts (namespace, pod, deployment, NetworkPolicy). The only routing input they touch is the optional `agent.runtime_endpoint` string column. Everything else is Helm-managed.

### Supervisor Outside K8s — Endpoint Injection
The supervisor is a docker-compose service (same deploy path as API/Admin), not a K8s workload. The only thing in K3s/EKS is the agent runtime environment pool. Callers look up `agent.runtime_endpoint` and pass it in each publish body. `runtime_endpoint=null` → `SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT` (dev: `http://k8s:30300`, the K3s container's NodePort; prod: env's Service DNS or LB URL).

### Abort Flow — No Pod Routing Required
The TCP connection from supervisor to a runtime pod is pinned once established (kube-proxy load-balances at connect time, not per-request). So **cancelling the supervisor's outbound httpx stream is sufficient** to abort the specific pod handling it:

```
WS disconnect / explicit abort
  → API POST /v1/sessions/{sid}/abort  (or just closes the publish conn)
  → supervisor._active[(sid, aid)].cancel()
  → httpx client context exits → TCP close → pod's req.on("close") → abortController.abort()
```

No pod-IP tracking, no runtime-side Redis signal, no per-replica affinity is required at the HTTP layer. **Multi-replica** is handled by a supervisor-only Redis fan-out: if `/abort` lands on a replica that doesn't hold the task, it publishes to the `supervisor:abort` channel and whichever replica holds the task cancels it. Runtime has no knowledge of this and no Redis connectivity.

### claude-agent-sdk Multi-Turn (TypeScript)
Uses the `query()` function from `@anthropic-ai/claude-agent-sdk`. TS SDK doesn't expose a `sessionId` option — Aviary session_id is injected via `extraArgs: { "session-id": sessionId }` which passes `--session-id <uuid>` to the CLI on the first message. Subsequent messages use `resume: sessionId` to load existing conversation history. Resume is determined by checking for existing JSONL in `<claudeDir>/projects/`. CLI session data persists on the environment PVC under `sessions/{sid}/agents/{aid}/.claude`. Runtime is a Node.js/Express server (`src/server.ts`). Agent config (instruction, tools, MCP servers) is sent in every message request body — no ConfigMap or on-disk config. `agent_id` arrives in `agent_config.agent_id`.

### Multi-Agent, Multi-Session Runtime
Each runtime Pod serves every agent. The SessionManager keys entries by `(session_id, agent_id)` and serializes messages per-key. There is **no hard concurrency cap** — the runtime accepts every request; scaling is handled at the infra level (add more pods / environments via Helm).

### Session Isolation (bubblewrap + single PVC)
The `claude` binary in PATH is a wrapper script (`scripts/claude-sandbox.sh`). The real binary is renamed to `claude-real` at build time (see Dockerfile). SDK must use `pathToClaudeCodeExecutable: "/usr/local/bin/claude"` to bypass the bundled binary and use the wrapper.

The environment's single RWX PVC is mounted at `/workspace-root` in every pod. Inside it:

```
/workspace-root/sessions/{sid}/shared/                 # shared across agents in the session
/workspace-root/sessions/{sid}/agents/{aid}/.claude/   # per-(agent, session) CLI context
/workspace-root/sessions/{sid}/agents/{aid}/.venv/     # per-(agent, session) Python venv
```

When the SDK invokes `claude`, the wrapper reads `SESSION_WORKSPACE` / `SESSION_CLAUDE_DIR` / `SESSION_VENV_DIR` / `SESSION_TMP` and runs `claude-real` inside a bwrap mount namespace:
- `/workspace-shared/` — empty tmpfs (hides the host layout).
- `SESSION_WORKSPACE` → `/workspace` — session-shared area; every agent in the session sees the same files.
- `SESSION_CLAUDE_DIR` → `/workspace/.claude` — per-(agent, session) CLI context overlay.
- `SESSION_VENV_DIR` → `/workspace/.venv` — per-(agent, session) Python venv.
- `SESSION_TMP` (`/tmp/{aid}_{sid}`) → `/tmp` — per-(agent, session) temp files.
- PID namespace isolated.

Other agents' / sessions' files are invisible inside the bwrap view.

### GitHub Token Injection
The API server fetches the user's GitHub token from Vault (`secret/aviary/credentials/{sub}/github-token`) on every message and passes it in `agent_config.credentials.github_token`. The runtime injects it as `GITHUB_TOKEN` and `GH_TOKEN` env vars, and configures a git credential helper (`scripts/git-credential-github.sh`) via `GIT_CONFIG_*` env vars. Inside the sandbox, both `git` and `gh` CLI are pre-authenticated.

### Egress Enforcement
Baseline NetworkPolicy (`charts/aviary-platform/templates/default-egress.yaml`) is always applied to every agent-runtime pod in the agents namespace. Environments can opt into additional egress rules via `charts/aviary-environment` values (`extraEgress`). K3s enforces NetworkPolicies via bundled kube-router.

### Claude Code Managed Settings
`runtime/config/managed-settings.json` is installed to `/etc/claude-code/managed-settings.json` (the hardcoded path Claude Code CLI reads on Linux). Currently sets `skipWebFetchPreflight: true` to prevent the CLI from calling `api.anthropic.com/api/web/domain_info` before each WebFetch — this endpoint is unreachable in air-gapped/fintech environments. All model tiers (`ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, etc.) are remapped to the agent's configured model in `src/agent.ts`.

### LiteLLM Adapter Streaming Patch
Non-Anthropic backends (Ollama, vLLM) use LiteLLM's Anthropic-to-OpenAI adapter. The patch file `config/litellm/patches/fix_adapter_streaming.py` fixes four issues: block type detection (thinking content), dropped trigger delta, thinking block flushing (periodic close/reopen for intermediate snapshots), and tool-call JSON cleanup (Gemma4 leaked tokens).

### Per-User Anthropic API Key
For Anthropic backends, each user's personal API key is injected from Vault via a LiteLLM `CustomLogger.async_pre_call_hook` (`config/litellm/patches/aviary_user_api_key.py`). The user's OIDC JWT is propagated from runtime to LiteLLM via `ANTHROPIC_CUSTOM_HEADERS` env var → `X-Aviary-User-Token` header. The hook validates the JWT, fetches the user's key from `secret/aviary/credentials/{sub}/anthropic-api-key`, and fails closed if the key is missing. Caching: JWKS 1h, JWT→sub 30min, Vault key 5min.

### Vault Credential Path Convention
Per-user credentials live at `secret/aviary/credentials/{user_external_id}/{key_name}` with JSON body `{"value": "<secret_string>"}`. Key names use `{service}-token` convention. The `user_external_id` is the OIDC `sub` claim from Keycloak.

### Streaming Architecture (Runtime)
The runtime (`runtime/src/agent.ts`) handles two streaming paths based on backend:
- **Anthropic backends**: emit raw `content_block_delta` events (token-level `text_delta` / `thinking_delta`). A `hasStreamDeltas` flag suppresses duplicate text/thinking from assistant snapshots.
- **Non-Anthropic backends** (Ollama, vLLM): text and thinking come from cumulative assistant snapshots, diffed against `emittedTextLen` / `emittedThinkingLen`. Shorter content = new block from flushing → counter resets.

### Chat Streaming Pipeline (API ↔ Supervisor ↔ Redis)
1. `api/app/services/stream/manager.py` reads `agent.runtime_endpoint` and POSTs to `/v1/sessions/{sid}/publish` (blocks until supervisor completes).
2. Supervisor streams SSE from `{runtime_endpoint}/message`, RPUSHes each event into `session:{id}:stream:chunks` (for replay) and PUBLISHes to `session:{id}:messages` (for live WS), and updates Prometheus counters.
3. On completion, supervisor rebuilds blocks (`app/assembly.py:rebuild_blocks_from_chunks`) and merges any A2A sub-agent events into `assembled_blocks`, returning `{status, reached_runtime, assembled_text, assembled_blocks}`.
4. API saves the returned message to DB, then publishes the `done` event with `messageId`. WS clients receive live events via independent Redis subscription.

Workflow engine and A2A sub-agent paths use the transparent `/v1/sessions/{sid}/message` passthrough because they do in-process event transformation rather than Redis assembly.

### Thinking Block Support
- **Supervisor** (`agent-supervisor/app/assembly.py`): `rebuild_blocks_from_chunks` folds `thinking` events into `blocks_meta` before `chunk` / `tool_use` events.
- **API cancel path** (`api/app/services/stream/blocks.py`): local rebuild used when the user disconnects mid-stream so the partial response still has structured blocks.
- **Frontend**: `ThinkingChip` renders real-time thinking; `SavedThinkingChip` renders persisted blocks.

### K8s Image Loading
All K8s custom images use `imagePullPolicy: Never`. Loaded via `docker save | docker compose exec -T k8s ctr images import -`. `setup-dev.sh` handles this for runtime and agent-supervisor. LiteLLM runs outside K8s and doesn't need image loading.

### K8s Fixed Node Name
`--node-name=aviary-node` in docker-compose.yml prevents stale node accumulation on container restart.

### PVC Strategy
One PVC per runtime environment (`aviary-env-<name>-workspace`). In dev the backing is a hostPath via K3s `local-path` on a docker volume (`k8sdata`); in prod it's an EFS volume with `efs-sc` storageClass and `ReadWriteMany`. The Helm values flip these (`pvc.storageClassName`, `pvc.accessMode`). Contents are keyed by `sessions/{sid}/…` so recreating an environment from scratch is explicit.

### React Strict Mode
Use `useRef` guards for WebSocket connections and OIDC callbacks to prevent duplicate execution in dev mode.

### Team Sync
Teams auto-synced from Keycloak/Okta `groups` claim on every login via `team_sync_service.py`.

## ACL Resolution (6 steps)

1. Agent owner → full access
2. Direct user ACL entry
3. Team ACL entries (highest role wins)
4. `visibility=public` → implicit `user` role
5. `visibility=team` → implicit `user` role if shared team with owner
6. Deny

Role hierarchy: `viewer` < `user` < `admin` < `owner`.

Note: there is no platform admin role in the API server. Operational work happens in the Admin Console (no auth, local-only) or via Helm.

## Testing

```bash
# API server tests
docker compose exec api pytest tests/ -v

# Admin console tests
docker compose exec admin pytest tests/ -v

# Supervisor tests (requires Redis env var)
cd agent-supervisor && uv run pytest tests/ -v
```

API/Admin: dedicated `aviary_test` database with `NullPool`, no lifespan.

## Rebuilding Images / Applying Chart Changes

**Runtime image** (K3s) — after modifying `runtime/`:

```bash
./scripts/quick-rebuild.sh runtime    # build + ctr import + rolling restart agent pods
```

**Supervisor** (docker compose) — after modifying `agent-supervisor/`:

```bash
./scripts/quick-rebuild.sh agent-supervisor    # docker compose up -d --build supervisor
```

**Helm chart changes** — render locally and apply via k3s kubectl:

```bash
docker run --rm -v "$PWD/charts:/charts:ro" alpine/helm:3.14.4 template \
  aviary-env-default /charts/aviary-environment -f /charts/aviary-environment/values-dev.yaml \
  --set hostGatewayIP=$K8S_GATEWAY_IP \
  | docker compose exec -T k8s kubectl apply -f -
```

`setup-dev.sh` does this automatically on first run.

**Docker Compose services** — hot reload via bind-mount, or `docker compose up -d --build <service>`.

## Key Environment Variables (API)

| Variable | Purpose |
|----------|---------|
| `OIDC_ISSUER` | Public Keycloak URL (token `iss` validation) |
| `OIDC_INTERNAL_ISSUER` | Internal Keycloak URL (discovery/JWKS fetch) |
| `DATABASE_URL` | PostgreSQL async connection |
| `REDIS_URL` | Redis for pub/sub, caching, presence |
| `VAULT_ADDR` / `VAULT_TOKEN` | Vault connection |
| `AGENT_SUPERVISOR_URL` | Agent Supervisor URL (default: `http://localhost:9000`) |
| `LITELLM_URL` | LiteLLM gateway URL (default: `http://litellm:4000`) |
| `LITELLM_API_KEY` | LiteLLM master key (default: `sk-aviary-dev`) |

## Key Environment Variables (Admin)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL async connection |

## Key Environment Variables (Runtime Pod)

| Variable | Purpose |
|----------|---------|
| `INFERENCE_ROUTER_URL` | LiteLLM gateway URL (`http://litellm.platform.svc:4000`) |
| `LITELLM_API_KEY` | LiteLLM master key (`sk-aviary-dev`) |
| `MCP_GATEWAY_URL` / `AVIARY_API_URL` / `AVIARY_INTERNAL_API_KEY` | Service URLs for runtime-side tools |

## Key Environment Variables (Agent Supervisor)

| Variable | Purpose |
|----------|---------|
| `REDIS_URL` | Redis DSN for publishing agent stream events (default: `redis://redis:6379/0`) |
| `SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT` | Fallback endpoint used when a caller passes `runtime_endpoint=null` |
| `METRICS_ENABLED` | Toggle Prometheus `/metrics` (default: true) |

## Key Environment Variables (LiteLLM Gateway)

| Variable | Purpose |
|----------|---------|
| `LITELLM_MASTER_KEY` | LiteLLM proxy auth key (default: `sk-aviary-dev`) |
| `VAULT_ADDR` / `VAULT_TOKEN` | Vault connection for per-user API key lookup |
| `OIDC_ISSUER` | Public Keycloak URL (JWT `iss` validation) |
| `OIDC_INTERNAL_ISSUER` | Internal Keycloak URL (JWKS fetch) |

## Key Environment Variables (MCP Gateway)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL async connection |
| `MCP_GATEWAY_PORT` | Listen port (default: 8100) |
| `OIDC_ISSUER` | Public Keycloak URL (token `iss` validation) |
| `OIDC_INTERNAL_ISSUER` | Internal Keycloak URL (JWKS fetch) |
| `OIDC_CLIENT_ID` | OIDC client ID (default: `aviary-web`) |

### MCP Gateway

**MCP Gateway** (docker compose, `:8100`): Centralized tool proxy for all agent MCP tool calls. Acts as a single MCP server (Streamable HTTP) from the claude-agent-sdk's perspective, internally proxying to multiple backend MCP servers.

**Key features:**
- **Tool catalog**: Admin registers backend MCP servers via Admin Console. Tools are auto-discovered via MCP `tools/list` protocol.
- **ACL (default-deny)**: Admin grants server-level or tool-level access to users/teams.
- **Agent tool bindings**: Users select tools from the catalog and bind them to their agents.
- **OIDC auth**: User's Keycloak JWT is propagated from browser → API → stream_manager → runtime → MCP Gateway. Gateway validates directly via Keycloak JWKS.
- **Tool namespacing**: Tools are exposed as `{server_name}__{tool_name}`.

**Data flow:**
1. Admin registers MCP server (Admin Console → DB) and triggers tool discovery.
2. Admin creates ACL rules granting users/teams access.
3. User browses tools (API → DB, ACL-filtered) and binds them to an agent.
4. On chat message: API constructs `mcpServers` config with gateway URL + user JWT in headers.
5. Runtime passes config to claude-agent-sdk; SDK connects to gateway as HTTP MCP server.
6. Gateway validates JWT, checks ACL, returns filtered `tools/list`, proxies `tools/call` to backend.

**DB tables:** `mcp_servers`, `mcp_tools`, `mcp_agent_tool_bindings`, `mcp_tool_acl`

**Architecture principle:** Agent ID is NOT used for ACL — the user's permission to use a tool (verified at both bind-time and call-time) is the access control. User token is NOT forwarded to backend MCP servers.
