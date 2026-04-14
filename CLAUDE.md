# Aviary

Multi-tenant AI agent platform. Users create/configure agents via Web UI; each agent runs as a long-running K8s Deployment in the shared `agents` namespace, powered by claude-agent-sdk.

## Quick Start

```bash
./scripts/setup-dev.sh   # First time: builds everything, loads K8s images
docker compose up -d      # Subsequent: just start services
```

Services: Web (`:3000`), API (`:8000`), Admin (`:8001`), Keycloak (`:8080`, admin/admin), Vault (`:8200`), LiteLLM Gateway (`:8090`), MCP Gateway (`:8100`), Agent Supervisor (`:9000`).
Test accounts: `user1@test.com`, `user2@test.com` (all `password`).

## Architecture

```
Browser → Next.js (:3000) → API rewrite proxy → FastAPI (:8000) ─┐
                                                  │               │
                                                  ├─ Redis pub/sub ─┤
                                                  │               │
   WebSocket ◄───────────────── Redis subscribe ──┘               │
                                                                   ▼
                           Agent Supervisor (:9000) → K8s API ─ agents NS
                                    │                              │
                                    └─ SSE consume from pod ───────┘
                                    │
                                    └─ Redis publish (chunks + stream buffer)

Admin Console (:8001) → Agent Supervisor (:9000) → K8s API
      ↓
PostgreSQL

Platform services (docker compose):
  LiteLLM Gateway (:8090) → Portkey AI Gateway → Claude API / Ollama / vLLM / Bedrock
  MCP Gateway (:8100) → Backend MCP Servers (tool proxy with OIDC auth + ACL)

Platform services (K8s, platform namespace):
  Agent Supervisor (:9000, NodePort 30900) → K8s API
  KEDA (scaling), kube-router (NetworkPolicy enforcement — k3s builtin)

Agent runtime namespace (K8s, agents namespace):
  One Deployment per agent (selector: aviary/agent-id=<uuid>)
  Namespace-wide baseline NetworkPolicy + optional per-agent NP for extra SGs

Agent Pod outbound (enforced by NetworkPolicy):
  LLM / MCP / API (platform)          — always allowed by baseline
  External destinations (CIDR blocks) — only if agent's ServiceAccount adds them
```

### Service Responsibilities

Three backend services with distinct roles:

**API Server (`:8000`)** — User-facing. Agent CRUD (config only), OIDC auth, ACL, sessions, chat. Communicates with the Agent Supervisor via an abstract interface (`agent_supervisor.py`) using only `agent_id` and `session_id`. No infrastructure knowledge.

**Admin Console (`:8001`)** — Operator-facing. No authentication (local-only). Edits scaling bounds (`min_pods`, `max_pods`), resource limits, container image, and the agent's ServiceAccount binding. Calls the supervisor to apply these to K8s. Also manages ServiceAccounts + SG refs and per-user Vault credentials.

**Agent Supervisor (`:9000`)** — Activator + SSE publisher. Runs inside K8s. Backend-abstracted via `RuntimeBackend` protocol; current implementation is K3S, EKS Native/Fargate stubbed. Owns: Deployment/Service/PVC lifecycle, SA creation + NetworkPolicy binding for extra SGs, 0→1 activation on demand, KEDA `ScaledObject` creation. Consumes agent runtime SSE and publishes every event to Redis (chunks + pub/sub) so the API stays off the SSE path. Has a Redis client but no DB access.

**Shared DB package** (`shared/aviary_shared/`) — SQLAlchemy models, migrations, and session factory used by API + Admin. Migrations live at `shared/aviary_shared/db/migrations/` with alembic config at `shared/alembic.ini`.

**Key flows:**
- Agent creation → API saves config to DB (no `service_account_id` set → baseline egress only) + registers infra via supervisor → admin can later attach a ServiceAccount / adjust scaling
- Chat message → WebSocket → API's `stream_manager` calls supervisor `POST /v1/agents/{id}/sessions/{sid}/publish` → supervisor streams SSE from runtime and publishes each event to Redis → API re-assembles blocks from the Redis buffer on completion and saves to DB; WS clients receive live events via independent Redis subscription
- ServiceAccount / scaling edit → Admin updates DB + calls supervisor `ensure_agent` / `bind_identity`. NetworkPolicy / KEDA ScaledObject updates take immediate effect. No pod restart needed unless image changes.
- Agent config edit (instruction, tools, MCP servers) → API updates DB only. Passed to runtime on every message request body. No pod restart.

**Pod Strategy (agent-per-deployment, session-per-workdir):** Each agent gets a Deployment scaled from 0 to `max_pods` by KEDA (trigger: `COUNT(sessions WHERE status='active')`, target: 5 sessions/pod). Multiple sessions share the same pods, isolated by per-session bwrap workdirs. Supervisor handles the `0→1` cold-start synchronously (`ensure_active` patches replicas=1 before KEDA's next poll).

**LiteLLM Gateway** (docker compose, `:8090`): All LLM calls go through LiteLLM OSS proxy. Backend is determined by the model name prefix (e.g., `anthropic/claude-sonnet-4-6` → Claude API, `ollama/gemma4:26b` → Ollama, `vllm/...` → vLLM, `bedrock/...` → Bedrock). Natively compatible with Anthropic SDK (`/v1/messages`), so claude-agent-sdk works transparently. Configuration in `config/litellm/config.yaml`. API server queries it for model listing (`/model/info`). Supports virtual keys, rate limiting, and per-user API key injection. Two startup patches loaded via `.pth` file: `fix_adapter_streaming.py` fixes Anthropic-to-OpenAI adapter streaming for non-Anthropic backends (see "LiteLLM Adapter Streaming Patch" below); `aviary_user_api_key.py` injects per-user Anthropic API keys from Vault (see "Per-User Anthropic API Key" below).

**Portkey AI Gateway** (docker compose, internal `:8787`): Sits between LiteLLM and LLM backends as an AI gateway. LiteLLM routes all requests to Portkey via `api_base`, and Portkey forwards to the actual provider based on `x-portkey-provider` header. Provides guardrails, OpenTelemetry-based observability and tracing, request/response logging, and caching. Not exposed externally — only accessed by LiteLLM within the docker network.

**Agent Supervisor** (K8s platform namespace, `:9000`): Managed by `app/backends/` driver (K3S today). All endpoints are agent-id-centric:
- **Agent-centric** (used by API server): `POST /v1/agents/{id}/register|run`, `GET /ready|/wait`, `POST /sessions/{sid}/publish|/abort`, `DELETE /sessions/{sid}`. The `/publish` endpoint is the SSE consumer → Redis publisher.
- **Admin-facing** (used by admin console): `POST /v1/agents/{id}/ensure|/restart`, `PATCH /scale|/scale-to-zero`, `GET /status|/metrics`, `PUT|DELETE /identity`, `DELETE /deployment`.

No background loops. Scaling (1↔N↔0) is entirely KEDA-driven. Supervisor only does 0→1 cold-start activation on demand.

**Egress policy** is split into two layers:
- **Baseline** (`k8s/platform/default-egress.yaml`): namespace-wide `NetworkPolicy` selecting `aviary/role=agent-runtime`; allows DNS + platform NS + gateway ports (LiteLLM 8090, MCP 8100, API 8000). Always in effect.
- **Per-agent extras** (optional `ServiceAccount` binding): a `ServiceAccount` DB entity names a bundle of `sg_refs` (profile names). When an agent is bound, supervisor loads the referenced profiles from the `egress-profiles` ConfigMap, merges their egress rule fragments, and applies a per-agent `NetworkPolicy` scoped by `aviary/agent-id=<uuid>`. K8s NP evaluates as a disjunction, so this unions with baseline — matching AWS SG semantics.

Agents with `service_account_id=NULL` get only baseline. Admin's UI: "— baseline only —" dropdown option vs named SAs.

## Critical Patterns & Gotchas

### OIDC Dual-URL Pattern
Keycloak tokens have `iss=http://localhost:8080/...` (browser URL), but API container must fetch OIDC metadata from `http://keycloak:8080/...` (internal DNS). Two env vars: `OIDC_ISSUER` (public, for token validation) and `OIDC_INTERNAL_ISSUER` (internal, for discovery/JWKS/exchange). See `_rewrite_url()` / `to_public_url()` in `auth/oidc.py`.

### Pydantic v2 `model_config` Conflict
`model_config` is a reserved Pydantic class variable. Use `Field(alias="model_config")` with `model_config_data` as the Python field name. The `model_config = {...}` class var must be declared BEFORE field definitions. See `api/app/schemas/agent.py`.

### API Server Knows Nothing About Infrastructure
The API server (`api/`) has no K8s concepts (namespace, pod, deployment, NetworkPolicy). It talks to the supervisor via `agent_supervisor.py` using only `agent_id` and `session_id`. Policy / SA / scaling is owned by the admin console; the API never reads or writes those fields.

### Backend Abstraction (`agent-supervisor/app/backends/`)
Supervisor logic is split behind a `RuntimeBackend` protocol (`backends/protocol.py`) composed of `WorkspaceStore` (PV/PVC provisioning), `IdentityBinder` (SA + SG binding), and lifecycle methods. `BACKEND_KIND` env var selects `k3s` / `eks_native` / `eks_fargate`. Only K3S is fully implemented; EKS entries are stubs for future work (EFS access points, `SecurityGroupPolicy`, Fargate profile). Router code never touches K8s directly — everything goes through the backend.

### claude-agent-sdk Multi-Turn (TypeScript)
Uses the `query()` function from `@anthropic-ai/claude-agent-sdk` (TypeScript). TS SDK doesn't expose a `sessionId` option — Aviary session_id is injected via `extraArgs: { "session-id": sessionId }` which passes `--session-id <uuid>` to the CLI on the first message. Subsequent messages use `resume: sessionId` to load existing conversation history. Resume is determined by checking for existing JSONL in `<workspace>/.claude/projects/`. CLI session data persists on PVC at `<workspace>/.claude/`, accessible inside the bwrap sandbox at `/home/usr/.claude` (HOME=/home/usr). Runtime is a Node.js/Express server (`src/server.ts`) — no Python dependency. Agent config (instruction, tools, MCP servers) is sent by the API server in every message request body — no ConfigMap or on-disk config. MCP servers from agent config are passed through to the SDK via `mcpServers` option. The runtime emits a final `result` SSE event with metadata (`total_cost_usd`, `usage`, `duration_ms`, `num_turns`) from the SDK's `ResultMessage` — the API can opt in to consuming this for billing/logging.

### Multi-Session Runtime
Each runtime Pod runs a `SessionManager` that tracks active sessions, enforces concurrency limits (`MAX_CONCURRENT_SESSIONS` env var, default 10), and serializes messages per-session. The readiness probe returns 503 when at capacity, preventing new session routing.

### Session Isolation (bubblewrap)
The `claude` binary in PATH is a wrapper script (`scripts/claude-sandbox.sh`). The real binary is renamed to `claude-real` at build time (see Dockerfile). SDK must use `pathToClaudeCodeExecutable: "/usr/local/bin/claude"` to bypass the bundled binary and use the wrapper. (node:22-slim puts npm global binaries in `/usr/local/bin/`, unlike the old python:3.12-slim + nodesource setup which used `/usr/bin/`.) When the SDK invokes `claude`, the wrapper reads `SESSION_WORKSPACE` from env (set per-session in `src/agent.ts`) and runs `claude-real` inside a bwrap mount namespace where:
- `/workspace-shared/` is an empty tmpfs (hides other sessions' shared homes)
- `$SESSION_WORKSPACE` (`/workspace-shared/{session_id}`) is bind-mounted to `/workspace` — shared across all agents in the session (hostPath, backed by `shared_workspace` docker volume in dev so it survives K3s container rebuilds)
- `$SESSION_CLAUDE_DIR` (`/workspace/.claude/{session_id}`) is bind-mounted to `/workspace/.claude` — per-agent CLI context overlay (PVC)
- `$SESSION_VENV_DIR` (`/workspace/.venvs/{session_id}`) is bind-mounted to `/workspace/.venv` — per-(agent, session) Python venv overlay (PVC). Per-agent so concurrent `pip install`s from different agents on the same session don't race on a shared venv. `PIP_CACHE_DIR` lives in the shared workspace so wheel downloads are still reused across agents.
- `$SESSION_TMP` (`/tmp/{session_id}`) is bind-mounted to `/tmp` — per-agent temp files (NOT shared across agents)
- PID namespace is isolated

All agents in the same session share `/workspace` via hostPath, enabling seamless file exchange. `/tmp` is per-agent (not shared across Pods). CLI session data (`.claude/`) and the Python venv (`.venv/`) are per-agent (PVC overlays), so conversation histories and pip installs don't collide. Other sessions' files are invisible.

### GitHub Token Injection
The API server fetches the user's GitHub token from Vault (`secret/aviary/credentials/{sub}/github-token`) on every message and passes it in `agent_config.credentials.github_token`. The runtime injects it as `GITHUB_TOKEN` and `GH_TOKEN` env vars, and configures a git credential helper (`scripts/git-credential-github.sh`) via `GIT_CONFIG_*` env vars. Inside the sandbox, both `git` and `gh` CLI are pre-authenticated — no MCP server needed for GitHub operations.

### KEDA-Driven Scaling
Supervisor creates one `ScaledObject` per agent on `register_agent` (builder at `backends/_common/keda.py`). Trigger: PostgreSQL scaler counting active sessions (`SELECT COUNT(*) FROM sessions WHERE agent_id=$1 AND status='active'`), target 5 sessions/pod. `minReplicaCount=min_pods` (default 0), `maxReplicaCount=max_pods` (default 3), `cooldownPeriod=300s`. 0→1 cold-start is handled by supervisor's `ensure_active` (direct `replicas=1` patch) because KEDA polling would add up to 30s to first-request latency. KEDA takes over for 1→N and N→0. Requires a pre-provisioned `TriggerAuthentication` `aviary-postgres-auth` referencing a DB DSN `Secret` in the `agents` namespace.

### Egress Enforcement
Two layers:
- **Baseline NetworkPolicy** (`k8s/platform/default-egress.yaml`) — installed by `setup-dev.sh`, selects `aviary/role=agent-runtime` pods in the `agents` namespace. Allows DNS + platform NS + gateway ports (LiteLLM 8090, MCP 8100, API 8000). Always in effect.
- **Per-agent extras** — optional. If the agent has a DB `ServiceAccount` attached, `admin.agent_lifecycle.sync_identity` → `supervisor.bind_identity(sg_refs)` merges the referenced profiles from the `egress-profiles` ConfigMap into a per-agent NetworkPolicy scoped by `aviary/agent-id=<uuid>`. Empty `sg_refs` / `service_account_id=NULL` → per-agent NP is deleted (baseline only).

K3s enforces NetworkPolicies via bundled kube-router even with flannel CNI.

### Claude Code Managed Settings
`runtime/config/managed-settings.json` is installed to `/etc/claude-code/managed-settings.json` (the hardcoded path Claude Code CLI reads on Linux). Currently sets `skipWebFetchPreflight: true` to prevent CLI from calling `api.anthropic.com/api/web/domain_info` before each WebFetch — this endpoint is unreachable in air-gapped/fintech environments. All model tiers (`ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, etc.) are remapped to the agent's configured model in `src/agent.ts` so that CLI internal tasks (WebFetch summarization, subagents) route through LiteLLM.

### LiteLLM Adapter Streaming Patch
Non-Anthropic backends (Ollama, vLLM) use LiteLLM's Anthropic-to-OpenAI adapter (`/v1/messages` → `/v1/chat/completions`). The adapter has streaming issues that are fixed by a monkeypatch loaded at startup via `.pth` file. The patch file is `config/litellm/patches/fix_adapter_streaming.py`, mounted into the LiteLLM container. It fixes four issues:

1. **Block type detection**: Adds `reasoning_content` check so thinking content from Ollama/OpenRouter gets its own `thinking` content block instead of being mixed into `text`.
2. **Dropped trigger delta**: Recovers the first delta lost during block transitions (e.g., thinking → text).
3. **Thinking block flushing**: Periodically closes/reopens thinking blocks (every 10 deltas) at the SSE byte layer so the CLI emits intermediate `assistant` snapshots for real-time thinking streaming. Text blocks are NOT flushed — internal CLI calls (WebFetch, subagents) expect a single text block.
4. **Tool call JSON cleanup**: Buffers `input_json_delta` events and cleans leaked Gemma4 special tokens (`<|\`, `<|\"|`) from the accumulated JSON before emitting. Uses `json.loads()` as a guard — clean JSON from other backends passes through untouched.

### Per-User Anthropic API Key
For Anthropic backends, each user's personal API key is injected from Vault via a LiteLLM `CustomLogger.async_pre_call_hook` (`config/litellm/patches/aviary_user_api_key.py`). The user's OIDC JWT is propagated from runtime to LiteLLM via `ANTHROPIC_CUSTOM_HEADERS` env var (set in `runtime/src/agent.ts`), which the Anthropic SDK includes as the `X-Aviary-User-Token` header. The hook validates the JWT against Keycloak JWKS, extracts the `sub` claim, and fetches the user's Anthropic API key from Vault at `secret/aviary/credentials/{sub}/anthropic-api-key`. If no key is found, the request is rejected with an error (no fallback to project default). Non-Anthropic backends (Ollama, vLLM) skip the hook entirely. Caching: JWKS 1h, JWT→sub 30min, Vault key 5min.

### Vault Credential Path Convention
All per-user credentials (MCP tool secrets, API keys) are stored at `secret/aviary/credentials/{user_external_id}/{key_name}` with JSON body `{"value": "<secret_string>"}`. Key names use `{service}-token` convention (e.g., `github-token`, `anthropic-api-key`, `jira-token`). The `user_external_id` is the OIDC `sub` claim from Keycloak. Admin console provides a UI for managing these credentials per user. Used by MCP Gateway (tool credential injection), LiteLLM (per-user API key), and the API server (GitHub token injection into sandbox).

### Streaming Architecture (Runtime)
The runtime (`runtime/src/agent.ts`) handles two distinct streaming paths based on backend:

- **Anthropic backends**: Emit `stream_event` messages with raw `content_block_delta` events (token-level `text_delta` and `thinking_delta`). These are forwarded directly for real-time streaming. A `hasStreamDeltas` flag is set on first `stream_event`, causing `assistant` snapshot text/thinking to be skipped (only `tool_use` is extracted from snapshots).
- **Non-Anthropic backends** (Ollama, vLLM): Don't emit `stream_event` deltas. Text and thinking are extracted from cumulative `assistant` snapshots by diffing against previously emitted lengths (`emittedTextLen`, `emittedThinkingLen`). When content length is shorter than tracked (= new block from flushing), the counter resets.

Both paths share the same counters so they never double-emit.

### Chat Streaming Pipeline (API ↔ Supervisor ↔ Redis)
The API server stays off the SSE data path. On a new message:
1. `api/app/services/stream/manager.py` → POST `/v1/agents/{id}/sessions/{sid}/publish` (blocks until supervisor completes).
2. Supervisor opens SSE to the runtime pod, and for every event: `redis_client.append_stream_chunk` (list for replay) + `redis_client.publish_message` (pub/sub for live WS). Returns `{status, reached_runtime}`.
3. API fetches the full chunk list from Redis, uses `rebuild_blocks_from_chunks` + `merge_a2a_events` to assemble the final message, writes to DB, then publishes the `done` event with `messageId`.
4. WS clients subscribe to `session:{id}:messages` pub/sub independently — they receive the live event stream without the API parsing SSE.

Workflow engine and A2A sub-agent paths (`routers/a2a.py`, `services/workflow_engine.py`) still use the older SSE `/message` endpoint — they need in-process event transformation, not the Redis bus.

### Thinking Block Support
- **stream_manager** (`api/app/services/stream/manager.py`): block assembly happens in `rebuild_blocks_from_chunks` — `thinking` events are folded into `blocks_meta` before `chunk` / `tool_use` events, preserving order in the saved message.
- **Frontend**: `ThinkingChip` component (collapsible, default open during streaming) renders real-time thinking content. Saved messages restore thinking blocks via `SavedThinkingChip` (default closed). Thinking blocks are part of the `StreamBlock` union type alongside `TextBlock` and `ToolCallBlock`.

### K8s Image Loading
All K8s custom images use `imagePullPolicy: Never`. Loaded via `docker save | docker compose exec -T k8s ctr images import -`. The `setup-dev.sh` handles this for runtime and agent-supervisor images. LiteLLM runs outside K8s as a docker compose service using the official image and doesn't need image loading.

### K8s Fixed Node Name
`--node-name=aviary-node` in docker-compose.yml prevents stale node accumulation on container restart. Without it, PVCs bind to old node names causing scheduling failures.

### PVC Strategy
Each agent gets a static, cluster-scoped PV named `agent-{agent_id}-workspace` (K3S `WorkspaceStore.ensure_agent_workspace`), bound 1:1 to a PVC of the same name in the `agents` namespace. PV uses a deterministic hostPath at `/var/lib/aviary/agent-workspace/{agent_id}/` instead of the `local-path` provisioner — this lets `quick-rebuild full` wipe `k8sdata` (etcd + image cache) without losing chat history or per-agent Python venvs (`.venvs/{session_id}/`). The host directory is backed by a dedicated docker volume (`agent_workspace_pv`), independent of K3s cluster state. The cross-agent shared session workspace (`/workspace-shared`) is similarly backed by a separate `shared_workspace` docker volume. Reclaim policy is `Retain` so host directories survive an accidental PV delete. Multi-node EKS migration would replace hostPath with EFS access points (`eks_fargate` backend stub).

`supervisor.unregister_agent` is the full teardown — removes Deployment, Service, PVC, PV, NetworkPolicy, and ScaledObject. Host directory survives (Retain); ops can clean up `/var/lib/aviary/agent-workspace/{agent_id}/` separately if disk pressure becomes an issue.

### React Strict Mode
Use `useRef` guards for WebSocket connections and OIDC callbacks to prevent duplicate execution in dev mode.

### Team Sync
Teams auto-synced from Keycloak/Okta `groups` claim on every login via `team_sync_service.py`. No manual team management.

## ACL Resolution (6 steps)

1. Agent owner → full access
2. Direct user ACL entry
3. Team ACL entries (highest role wins)
4. `visibility=public` → implicit `user` role
5. `visibility=team` → implicit `user` role if shared team with owner
6. Deny

Role hierarchy: `viewer` < `user` < `admin` < `owner`.

Note: There is no platform admin role in the API server. All administrative operations (infrastructure, policy, scaling) are performed via the admin console which has no authentication.

## Testing

```bash
# API server tests
docker compose exec api pytest tests/ -v

# Admin console tests
docker compose exec admin pytest tests/ -v
```

API: Tests using dedicated `aviary_test` database with `NullPool` (avoids asyncpg conflicts). Test app has no lifespan (no background tasks). Mock auth via `_TOKEN_CLAIMS` dict mapping tokens to claims for multi-user scenarios.

Admin: Tests use the same test database pattern. No auth mocking needed (admin has no authentication). Supervisor calls are mocked.

## Rebuilding Images

**K8s images** (runtime, agent-supervisor) — after modifying `runtime/` or `agent-supervisor/`:

```bash
docker build -t aviary-runtime:latest ./runtime/
docker build -t aviary-agent-supervisor:latest -f agent-supervisor/Dockerfile .
docker save aviary-runtime:latest aviary-agent-supervisor:latest | docker compose exec -T k8s ctr images import -
```

**Docker Compose services** (api, admin) — hot reload via bind-mount, or rebuild:

```bash
docker compose up -d --build api admin
```

**LiteLLM Gateway** — edit `config/litellm/config.yaml` and restart:

```bash
docker compose restart litellm
```

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
| `AGENT_SUPERVISOR_URL` | Agent Supervisor URL (default: `http://localhost:9000`) |

## Key Environment Variables (Runtime Pod)

| Variable | Purpose |
|----------|---------|
| `AGENT_ID` | Agent UUID |
| `MAX_CONCURRENT_SESSIONS` | Max sessions per pod (default: 10) |
| `INFERENCE_ROUTER_URL` | LiteLLM gateway URL (`http://litellm.platform.svc:4000`) |
| `LITELLM_API_KEY` | LiteLLM master key (`sk-aviary-dev`) |

## Key Environment Variables (Agent Supervisor)

| Variable | Purpose |
|----------|---------|
| `BACKEND_KIND` | `k3s` (default) / `eks_native` / `eks_fargate` |
| `DATABASE_URL` | PostgreSQL DSN — only for KEDA's `TriggerAuthentication`; supervisor itself doesn't connect |
| `REDIS_URL` | Redis DSN for publishing agent stream events (default: `redis://redis:6379/0`) |
| `AGENT_RUNTIME_IMAGE` | Container image for agent Pods (default: `aviary-runtime:latest`) |
| `HOST_GATEWAY_IP` | Host IP for Pod hostAliases (injected by setup script) |
| `MAX_CONCURRENT_SESSIONS_PER_POD` | KEDA scaling target, sessions per pod (default: 5) |
| `INFERENCE_ROUTER_URL` / `LITELLM_API_KEY` | Injected into runtime pod env |
| `MCP_GATEWAY_URL` / `AVIARY_API_URL` / `INTERNAL_API_KEY` | Injected into runtime pod env |

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
- **ACL (default-deny)**: Admin grants server-level or tool-level access to users/teams. Users can only see and bind tools they have `use` permission for.
- **Agent tool bindings**: Users select tools from the catalog and bind them to their agents. Bindings stored in `mcp_agent_tool_bindings` table.
- **OIDC auth**: User's Keycloak JWT is propagated from browser → API → stream_manager → runtime → MCP Gateway. Gateway validates the JWT directly via Keycloak JWKS (same dual-URL pattern as API server).
- **Tool namespacing**: Tools are exposed as `{server_name}__{tool_name}` (double underscore separator).

**Data flow:**
1. Admin registers MCP server (Admin Console → DB) and triggers tool discovery
2. Admin creates ACL rules granting users/teams access to servers/tools
3. User browses tools (API → DB, ACL-filtered) and binds them to agent
4. On chat message: API constructs `mcpServers` config with gateway URL + user JWT in headers
5. Runtime passes config to claude-agent-sdk; SDK connects to gateway as HTTP MCP server
6. Gateway validates JWT, checks ACL, returns filtered `tools/list`, proxies `tools/call` to backend

**DB tables:** `mcp_servers`, `mcp_tools`, `mcp_agent_tool_bindings`, `mcp_tool_acl`

**Architecture principle:** Agent ID is NOT used for ACL — the user's permission to use a tool (verified at both bind-time and call-time) is the access control. User token is NOT forwarded to backend MCP servers.
