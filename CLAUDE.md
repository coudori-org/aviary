# Aviary

Multi-tenant AI agent platform. Users create/configure agents via Web UI; every agent runs in a **shared runtime environment** (a pre-provisioned K8s Deployment pool) powered by claude-agent-sdk.

## Quick Start

```bash
./scripts/dev-up.sh                          # Boots local-infra + services (idempotent)
./scripts/dev-down.sh                        # Tear down (volumes preserved)

# Iterating on a single service:
docker compose up -d --build api             # rebuild + restart api (project root)
cd local-infra && docker compose restart litellm   # tweak litellm config

# Helm chart validation (separate flow — K3s is opt-in):
./scripts/chart-test.sh
```

The repo is two compose stacks that mirror the production split:

- **[local-infra/](local-infra/)** — *local* simulation of what the platform team runs in prod (postgres, redis, keycloak, vault, temporal, litellm, prometheus, grafana, mcp-jira/confluence, optional K3s under the `k3s` profile). Exists only because we don't have prod infra reachable from a dev box.
- **Project root** — the services we own end-to-end and ship through CI/CD as container images (api, admin, web, agent-supervisor, workflow-worker). The root `compose.yml` wires them together for local dev; each connects to local-infra via `host.docker.internal:<port>` so the two stacks stay loosely coupled.

Services: Web (`:3000`), API (`:8000`), Admin (`:8001`), Keycloak (`:8080`, admin/admin), Vault (`:8200`), LiteLLM Gateway (`:8090`, inference + aggregated MCP at `/mcp`), Agent Supervisor (`:9000`), Temporal UI (`:8233`), Prometheus (`:9090`), Grafana (`:3001`).
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

Project root (docker compose — what we ship via CI/CD):
  api, admin, agent-supervisor, workflow-worker, web, db-migrate

local-infra/ (docker compose — pre-provisioned in prod, simulated locally):
  Postgres, Redis, Keycloak, Vault, Temporal, LiteLLM (:8090 — inference + MCP),
  Prometheus, Grafana, mcp-jira / mcp-confluence, optional K3s (profile: k3s)

K8s cluster (Helm-managed; the only thing in K3s/EKS):
  charts/aviary-platform — namespaces, baseline egress NP,
    external-services proxy Services (dev only), image-warmer DaemonSet
    (optional), shared RWX workspace PVC (mounted by every env)
  charts/aviary-environment — one release per runtime environment:
    Deployment (replicas fixed, min 1) — pool serves every agent
    Service (NodePort in dev → supervisor hits host.docker.internal:<port>;
            ClusterIP in prod)
    optional per-env NetworkPolicy (union with baseline)

Agent routing:
  agent.runtime_endpoint (nullable) in the DB.
  null → supervisor's SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT (default env).
  non-null → any env Service DNS (admin sets per agent).

Environments shipped out of the box (both `charts/aviary-environment` releases):
  default — locked-down egress (DNS + platform only), base `aviary-runtime`
            image (git + gh). NodePort 30300 — the supervisor's default.
  custom  — worked example of a per-env customization: open internet via
            `extraEgress: 0.0.0.0/0` and `aviary-runtime-custom` image
            (base + `cowsay` as a demo marker, see runtime/Dockerfile.custom).
            NodePort 30301. Point an agent at this env by setting
            agent.runtime_endpoint = http://host.docker.internal:30301 in
            the admin console (dev) or the env's in-cluster Service DNS (prod).
```

### Service Responsibilities

Three backend services with distinct roles:

**Access model (current)** — *Owner-only* for every entity (agent, session, workflow). There is no ACL, no team, no visibility, no platform-admin, no invited participants. RBAC will return later as a dedicated redesign; everything below assumes a single-owner world.

**API Server (`:8000`)** — User-facing. Agent/session/workflow CRUD (owner-only), OIDC auth, chat. Looks up the agent row, builds a self-contained `agent_config`, and POSTs to the supervisor with `Authorization: Bearer <user JWT>`. Subscribes to the session's Redis channel and relays every event to WS clients. Also publishes the DB-consistent events (`user_message` on WS receive, `done`/`cancelled`/`error` after persisting the agent message) and maintains per-user unread counters — those require DB ids and the session participant list, which the supervisor doesn't know. No Vault client. No K8s concepts.

**Admin Console (`:8001`)** — Operator-facing. No authentication (local-only). Manages agent / workflow definitions only. User management, per-user Vault credentials, and MCP server CRUD have been removed — users self-serve credentials through the Web UI, and MCP servers are provisioned via LiteLLM directly (YAML config or its own UI). Runtime infrastructure is Helm-managed — admin never talks to K8s or the supervisor.

**Agent Supervisor (`:9000`, project-root compose)** — Reverse SSE Proxy. Runs outside K8s, same deploy unit as API/Admin. No DB, no K8s API. Holds an **in-memory registry** of active stream tasks keyed by **stream_id** (one per `/message` call). `/sessions/{sid}/message` and `/sessions/{sid}/a2a` require `Authorization: Bearer <user JWT>` — the supervisor validates the token via OIDC and owns per-user runtime credential lookup: it fetches `github-token` from Vault using the JWT's `sub` and injects `agent_config.credentials` / `user_token` / `user_external_id` into the request body before forwarding to the runtime. On each `/message` it allocates a `stream_id` and immediately publishes `stream_started {stream_id}` to `session:{sid}:events` — that's the frontend's confirmation signal for enabling the abort button. Streams SSE from the runtime's Service endpoint, publishes every stream event (tagged with stream_id) to `session:{sid}:events`, buffers chunks under `stream:{stream_id}:chunks` for replay, assembles the final text + blocks, returns them to the caller — the API then persists the message and publishes the terminal `done`/`cancelled` event with the DB messageId. Emits Prometheus metrics at `/metrics`. **Abort** = `POST /v1/streams/{stream_id}/abort` → cancel the task; closing the outbound httpx stream propagates close through the Service-pinned TCP connection, which fires `res.on("close")` in the runtime pod and aborts the SDK.

**Shared DB package** ([shared/aviary_shared/](shared/aviary_shared/)) — SQLAlchemy models, migrations, and session factory used by API + Admin. Migrations live at [shared/aviary_shared/db/migrations/](shared/aviary_shared/db/migrations/) with alembic config at [shared/alembic.ini](shared/alembic.ini).

**Key flows:**
- Agent creation → API saves config to DB. No infrastructure side effects.
- Agent routing edit → Admin updates `agent.runtime_endpoint` in DB. Effective on the next chat message.
- Chat message → WebSocket → API saves the user message to DB and publishes `user_message {messageId}` to `session:{sid}:events`, builds the full `agent_config` (runtime_endpoint, model_config, instruction, tools, mcp_servers, optional accessible_agents), POSTs `supervisor /v1/sessions/{sid}/message` with `Authorization: Bearer <user JWT>` → supervisor allocates a stream_id, publishes `stream_started {stream_id}` so the client can enable the abort button, validates the JWT, fetches Vault credentials, injects them into `agent_config`, streams SSE from `{endpoint}/message`, publishes every stream event to `session:{sid}:events` and buffers under `stream:{stream_id}:chunks`, assembles final text + blocks, returns them → API persists the agent message to DB, publishes `done {messageId}` (or `cancelled {messageId}` when the supervisor returned `status=aborted`), and INCRs `session:{sid}:unread:{uid}` for every session participant. Any WS actively relaying the terminal event clears its own user's unread counter on the same transition.
- Agent config edit (instruction, tools, MCP servers) → API updates DB only. Passed to runtime on every message request body.

**Pod Strategy (env-per-pool, (agent, session)-per-workdir):** One Helm release per environment. Replicas fixed (min 1), no scale-to-zero. Every pod serves every agent. Isolation comes from per-(agent, session) on-disk paths plus bubblewrap — the pod itself is agent-agnostic.

**LiteLLM Gateway** (local-infra/ compose, `:8090`): All LLM calls go through LiteLLM OSS proxy. Backend is determined by the model name prefix (e.g., `anthropic/claude-sonnet-4-6` → Claude API, `ollama/gemma4:26b` → Ollama, `vllm/...` → vLLM, `bedrock/...` → Bedrock). Natively compatible with Anthropic SDK (`/v1/messages`), so claude-agent-sdk works transparently. The same proxy also serves `/mcp` — the aggregated MCP endpoint (see "MCP Aggregation" below). Configuration in [local-infra/config/litellm/config.yaml](local-infra/config/litellm/config.yaml). Four patch modules loaded via `.pth` file:
- `aviary_user_api_key.py` — `CustomLogger.async_pre_call_hook` that validates the user's Keycloak JWT (forwarded as `X-Aviary-User-Token`), fetches per-user Anthropic API key from Vault, overrides the outgoing key. Fails closed.
- `aviary_mcp_credentials.py` — owns everything MCP: request-ingress JWT gate (plugs the OAuth2-passthrough fail-open), tools/list filter (X-Aviary-Allowed-Tools + RBAC stub), tools/call gate, and `pre_mcp_call` Vault-argument injection. Same JWKS/Keycloak validation as above.
- `aviary_jwt_util.py` — shared JWKS fetch + JWT validation + sub-cache helpers used by both patches above. JWKS has a forced-refetch cooldown so random-kid tokens can't DoS the IdP.
- `aviary_vault_util.py` — shared Vault credential fetch (`secret/aviary/credentials/{sub}/{key}`). No caching by design — profile changes must reflect immediately. Slow fetches log a warning.

LiteLLM UI (`http://localhost:8090/ui`, default `admin/admin`) is backed by a dedicated `litellm` Postgres database on the shared Postgres instance. LiteLLM applies its own Prisma migrations on startup. Keys, teams, and spend live in the DB; models stay file-only — `config.yaml` is the single source of truth. `STORE_MODEL_IN_DB` is left at its default (off) so `/v1/model/info` never surfaces UI-added shadow copies. Credentials come from `LITELLM_UI_USERNAME` / `LITELLM_UI_PASSWORD` env vars.

**Observability**: Prometheus (`:9090`, local-infra/) scrapes `host.docker.internal:9000/metrics` (the supervisor lives in the project-root compose — see [local-infra/config/prometheus/prometheus.yml](local-infra/config/prometheus/prometheus.yml)) every 15s with 7d retention. Grafana (`:3001`, anonymous admin in dev) auto-provisions the Prometheus datasource plus the "Aviary Supervisor" dashboard from [local-infra/config/grafana/dashboards/supervisor.json](local-infra/config/grafana/dashboards/supervisor.json) — panels cover active streams, publish request rate/error ratio, p50/p95/p99 publish duration, TTFB, SSE event mix, runtime HTTP errors, abort paths, and Vault/Redis dependency health.

**Agent Supervisor routes:**
- `POST /v1/sessions/{sid}/message` — Bearer-gated. Body: `{session_id, content_parts, agent_config}` where `agent_config` carries `runtime_endpoint`, `model_config`, `instruction`, `tools`, `mcp_servers`, optional `accessible_agents` (each is a full agent spec). Returns `{status, stream_id, reached_runtime, assembled_text, assembled_blocks}`. All stream events are published to Redis under `session:{sid}:events` tagged with the allocated `stream_id`.
- `POST /v1/sessions/{sid}/a2a` — Bearer-gated. Parent runtime's A2A MCP server invokes this with `{parent_session_id, parent_tool_use_id, agent_config: <full sub-agent config>, content_parts}`. Sub-agent SSE is forwarded to the caller; `tool_use`/`tool_result` events are tagged with `parent_tool_use_id` and stashed in the parent's A2A buffer for assembly merge.
- `POST /v1/streams/{stream_id}/abort` — cancel the registered task. Unknown stream → fan-out on `supervisor:abort` so whichever replica holds it cancels.
- `DELETE /v1/sessions/{sid}` — cleanup workspace directories for a given (agent, session).
- `GET /v1/health` · `GET /metrics` (Prometheus).

No background loops. No per-agent state. No 0↔1 activation — environments are always on.

**Egress policy** is set per environment via Helm:
- **Baseline** (`charts/aviary-platform/templates/default-egress.yaml`): namespace-wide `NetworkPolicy` on `aviary/role=agent-runtime`; allows DNS + platform NS + gateway ports (LiteLLM 8090 — inference + aggregated MCP, API 8000, Supervisor 9000 — for A2A). Always in effect.
- **Per-environment extras**: optional `extraEgress` list in `charts/aviary-environment/values.yaml` gets merged into a second NetworkPolicy scoped by `aviary/environment=<name>`. K8s NP evaluates as a disjunction — this unions with baseline.

## Critical Patterns & Gotchas

### IdP Switching — Pure Env, No Code Changes
All IdP wiring lives in `shared/aviary_shared/auth/` and is driven by env vars. The flag that picks the mode is `OIDC_ISSUER`:

- **`OIDC_ISSUER` unset** — no real IdP. `OIDCValidator` runs in null mode and resolves every token to a fixed `TokenClaims(sub=DEV_USER_SUB)` (default `dev-user`). The frontend calls `/api/auth/dev-login` instead of running PKCE; the supervisor accepts requests with no Bearer; LiteLLM patches use `dev-user` for Vault lookups. Pre-seed `secret/aviary/credentials/dev-user/{anthropic-api-key,github-token,…}` for whatever credentials the local stack needs.
- **`OIDC_ISSUER` set** — real OIDC validation kicks in. Aviary only consumes the standard `sub` / `email` / `name` claims, so any OIDC-compliant IdP (Keycloak, Okta, Auth0, …) works without a per-IdP claim mapper.

**Required env when enabling an IdP** (set on api + supervisor + LiteLLM):
- `OIDC_ISSUER` — public issuer URL. JWT `iss` claim must match.
- `OIDC_CLIENT_ID` — for the auth-code flow on the API server.
- `OIDC_CLIENT_SECRET` — only for confidential clients (e.g. Okta). Public PKCE clients (local Keycloak `aviary-web`) leave this unset.
- `OIDC_INTERNAL_ISSUER` — only when the public URL isn't reachable from inside the container (local Keycloak: `http://host.docker.internal:8080/...`). For hosted IdPs leave it unset.
- `OIDC_AUDIENCE` — optional `aud` claim check.

**OIDC dual-URL pattern**: tokens carry `iss=<public URL>`, but the API container needs the internal DNS for discovery/JWKS. `_rewrite_url()` / `to_public_url()` in `aviary_shared.auth.oidc` handle the swap whenever `OIDC_INTERNAL_ISSUER` differs.

The LiteLLM patches (`config/litellm/patches/aviary_jwt_util.py`) extract only the `sub` claim, which is standard across all OIDC providers — they share the same `OIDC_ISSUER` switch and fall through to `DEV_USER_SUB` when it's unset.

### Pydantic v2 `model_config` Conflict
`model_config` is a reserved Pydantic class variable. Use `Field(alias="model_config")` with `model_config_json` as the Python field name — the shared `MODEL_CONFIG_ALIAS` in `api/app/schemas/_common.py` centralizes this. The `ConfigDict(populate_by_name=True, protected_namespaces=())` class var must be declared BEFORE field definitions. See `api/app/schemas/agent.py`.

### API + Admin Know Nothing About Infrastructure
Neither service has K8s concepts (namespace, pod, deployment, NetworkPolicy). The only routing input they touch is the optional `agent.runtime_endpoint` string column. Everything else is Helm-managed.

### Supervisor Outside K8s — Endpoint Injection
The supervisor is a service in the project-root compose (same deploy path as API/Admin), not a K8s workload. The only thing in K3s/EKS is the agent runtime environment pool. Callers look up `agent.runtime_endpoint` and pass it in each publish body. `runtime_endpoint=null` → `SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT` (dev: `http://host.docker.internal:30300`, the K3s container's NodePort published by local-infra; prod: env's Service DNS or LB URL).

### Abort Flow — No Pod Routing Required
The TCP connection from supervisor to a runtime pod is pinned once established (kube-proxy load-balances at connect time, not per-request). So **cancelling the supervisor's outbound httpx stream is sufficient** to abort the specific pod handling it:

```
Frontend Stop button (knows stream_id from `stream_started` event)
  → WS {type: "cancel", stream_id}
  → API POST /v1/streams/{stream_id}/abort
  → supervisor._active[stream_id].cancel()
  → httpx client context exits → TCP close → pod's res.on("close") → abortController.abort()
```

Two subtle points the original design got wrong and had to be fixed:
1. **`res.on("close")`, not `req.on("close")`.** Node/Express's `req.on("close")` doesn't fire for in-flight streaming responses — a previous version missed every abort because of this.
2. **Client-driven `stream_id`.** The server doesn't remember "which stream is active for this session" — the frontend learns `stream_id` from the `stream_started` broadcast and sends it back on cancel. That's what unlocks per-user targeting when multi-participant sessions return.

**Multi-replica** is handled by a supervisor-only Redis fan-out: if `/abort` lands on a replica that doesn't hold the task, it publishes to the `supervisor:abort` channel with the `stream_id` and whichever replica holds it cancels. Runtime has no knowledge of this and no Redis connectivity.

### claude-agent-sdk Multi-Turn (TypeScript)
Uses the `query()` function from `@anthropic-ai/claude-agent-sdk`. TS SDK doesn't expose a `sessionId` option — Aviary session_id is injected via `extraArgs: { "session-id": sessionId }` which passes `--session-id <uuid>` to the CLI on the first message. Subsequent messages use `resume: sessionId` to load existing conversation history. Resume is determined by checking for existing JSONL in `<claudeDir>/projects/`. CLI session data persists on the **shared workspace PVC** under `sessions/{sid}/agents/{aid}/.claude` — so a session can migrate between environments (e.g., admin swaps `agent.runtime_endpoint`) without losing its history. Runtime is a Node.js/Express server (`src/server.ts`). Agent config (instruction, tools, MCP servers) is sent in every message request body — no ConfigMap or on-disk config. `agent_id` arrives in `agent_config.agent_id`.

### Multi-Agent, Multi-Session Runtime
Each runtime Pod serves every agent. The SessionManager keys entries by `(session_id, agent_id)` and serializes messages per-key. There is **no hard concurrency cap** — the runtime accepts every request; scaling is handled at the infra level (add more pods / environments via Helm).

### Session Isolation (bubblewrap + shared PVC)
The `claude` binary in PATH is a wrapper script (`scripts/claude-sandbox.sh`). The real binary is renamed to `claude-real` at build time (see Dockerfile). SDK must use `pathToClaudeCodeExecutable: "/usr/local/bin/claude"` to bypass the bundled binary and use the wrapper.

The cluster-wide shared RWX PVC (`aviary-shared-workspace`, owned by `aviary-platform`) is mounted at `/workspace-root` in every runtime pod, across every environment. Inside it:

```
/workspace-root/sessions/{sid}/shared/                 # shared across agents in the session
/workspace-root/sessions/{sid}/agents/{aid}/.claude/   # per-(agent, session) CLI context
/workspace-root/sessions/{sid}/agents/{aid}/.venv/     # per-(agent, session) Python venv
```

When the SDK invokes `claude`, the wrapper reads `SESSION_WORKSPACE` / `SESSION_CLAUDE_DIR` / `SESSION_VENV_DIR` / `SESSION_TMP` and runs `claude-real` inside a bwrap mount namespace:
- `/workspace-root/` — empty tmpfs overlay; hides the PVC layout so sibling sessions living under the same PVC can't be enumerated from inside the sandbox.
- `SESSION_WORKSPACE` → `/workspace` — session-shared area; every agent in the session sees the same files.
- `SESSION_CLAUDE_DIR` → `/workspace/.claude` — per-(agent, session) CLI context overlay.
- `SESSION_VENV_DIR` → `/workspace/.venv` — per-(agent, session) Python venv.
- `SESSION_TMP` (`/tmp/{aid}_{sid}`) → `/tmp` — per-(agent, session) temp files.
- PID namespace isolated.

Other agents' / sessions' files are invisible inside the bwrap view.

### GitHub Token Injection
The supervisor fetches the user's GitHub token from Vault (`secret/aviary/credentials/{sub}/github-token`) on every `/message` and `/a2a` call, keyed by the `sub` of the validated Bearer JWT, and injects it as `agent_config.credentials.github_token` into the outbound runtime request. The runtime exposes it as `GITHUB_TOKEN` / `GH_TOKEN` env vars and configures a git credential helper (`scripts/git-credential-github.sh`) via `GIT_CONFIG_*` env vars. Inside the sandbox both `git` and `gh` are available on every env and authenticated via `GITHUB_TOKEN` / `GH_TOKEN` env vars + git credential helper. Callers (API, parent runtime) MUST NOT put `credentials` / `user_token` / `user_external_id` in the body — the supervisor overwrites them with the authoritative validated identity.

### Egress Enforcement
Baseline NetworkPolicy (`charts/aviary-platform/templates/default-egress.yaml`) is always applied to every agent-runtime pod in the agents namespace. Environments can opt into additional egress rules via `charts/aviary-environment` values (`extraEgress`). K3s enforces NetworkPolicies via bundled kube-router.

### Claude Code Managed Settings
[runtime/config/managed-settings.json](runtime/config/managed-settings.json) is installed to `/etc/claude-code/managed-settings.json` (the hardcoded path Claude Code CLI reads on Linux). Currently sets `skipWebFetchPreflight: true` to prevent the CLI from calling `api.anthropic.com/api/web/domain_info` before each WebFetch — this endpoint is unreachable in air-gapped/fintech environments. All model tiers (`ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, etc.) are remapped to the agent's configured model in [runtime/src/agent.ts](runtime/src/agent.ts).

### Per-User Anthropic API Key
For Anthropic backends, each user's personal API key is injected from Vault via a LiteLLM `CustomLogger.async_pre_call_hook` ([local-infra/config/litellm/patches/aviary_user_api_key.py](local-infra/config/litellm/patches/aviary_user_api_key.py)). The user's OIDC JWT is propagated from runtime to LiteLLM via `ANTHROPIC_CUSTOM_HEADERS` env var → `X-Aviary-User-Token` header. The hook validates the JWT against Keycloak JWKS, fetches the user's key from `secret/aviary/credentials/{sub}/anthropic-api-key`, and fails closed if the key is missing. Caching: JWKS 1h, JWT→sub 30min (keyed on the whole token — not just the signature — to prevent a tampered-payload + original-signature collision), Vault key 30s.

### Vault Credential Path Convention
Per-user credentials live at `secret/aviary/credentials/{user_external_id}/{key_name}` with JSON body `{"value": "<secret_string>"}`. Key names use `{service}-token` convention. The `user_external_id` is the OIDC `sub` claim from Keycloak.

### Streaming Architecture (Runtime)
The runtime ([runtime/src/agent.ts](runtime/src/agent.ts)) handles two streaming paths based on backend:
- **Anthropic backends**: emit raw `content_block_delta` events (token-level `text_delta` / `thinking_delta`). A `hasStreamDeltas` flag suppresses duplicate text/thinking from assistant snapshots.
- **Non-Anthropic backends** (Ollama, vLLM): text and thinking come from cumulative assistant snapshots, diffed against `emittedTextLen` / `emittedThinkingLen`. Shorter content = new block from flushing → counter resets.

### Chat Streaming Pipeline (API ↔ Supervisor ↔ Redis)
1. API WS handler saves the user message to DB and builds the full `agent_config` (runtime_endpoint, model_config, instruction, tools, mcp_servers, optional accessible_agents).
2. API POSTs `/v1/sessions/{sid}/message` with `Authorization: Bearer <user JWT>` (blocks until supervisor completes).
3. Supervisor validates the JWT, allocates a `stream_id`, fetches per-user credentials (`github-token`) from Vault, injects `credentials`/`user_token`/`user_external_id` into `agent_config`.
4. Supervisor streams SSE from `{agent_config.runtime_endpoint}/message`, tags each event with `stream_id`, RPUSHes into `stream:{stream_id}:chunks` (for replay), PUBLISHes to `session:{sid}:events` (for live WS), and updates Prometheus counters.
5. On completion, supervisor rebuilds blocks (`app/assembly.py:rebuild_blocks_from_chunks`) and merges any A2A sub-agent events into `assembled_blocks`, returning `{status, stream_id, reached_runtime, assembled_text, assembled_blocks}`.
6. API persists the agent message to DB, then publishes a terminal event (`done {messageId}` on normal complete, `cancelled {messageId}` on abort, or `error {message, rollback_message_id?}` on failure) to the same `session:{sid}:events` channel. The API also writes the `user_message` event when a WS message is received, and manages `session:{sid}:unread:{uid}` counters (INCR per participant on terminal events, DEL when a watching WS forwards `done`/`cancelled`). Supervisor owns stream events; API owns DB-consistent events + unread.

### Thinking Block Support
- **Supervisor** ([agent-supervisor/app/assembly.py](agent-supervisor/app/assembly.py)): `rebuild_blocks_from_chunks` folds `thinking` events into `blocks_meta` before `chunk` / `tool_use` events. On abort, the same helper assembles whatever was buffered so the API gets a partial message to save.
- **Frontend**: `ThinkingChip` renders real-time thinking; `SavedThinkingChip` renders persisted blocks.

### K8s Image Loading
All K8s custom images use `imagePullPolicy: Never`. Loaded via `docker save | docker compose --profile k3s exec -T k8s ctr images import -` (the K3s container lives in [local-infra/compose.yml](local-infra/compose.yml) under the `k3s` profile). [scripts/chart-test.sh](scripts/chart-test.sh) handles this for the runtime images. LiteLLM runs outside K8s and doesn't need image loading.

### K8s Fixed Node Name
`--node-name=aviary-node` in [local-infra/compose.yml](local-infra/compose.yml) prevents stale node accumulation on container restart.

### PVC Strategy
One **shared RWX** PVC (`aviary-shared-workspace`) provisioned by `aviary-platform`, mounted by every runtime environment. Environments are capability boundaries (image + egress); data boundaries are `(agent_id, session_id)` on-disk paths. A session's Claude CLI history, shared files, and per-(agent, session) venv live under `sessions/{sid}/…` on this one PVC — so swapping `agent.runtime_endpoint` mid-session keeps the conversation intact.

Backing differs per env:
- **Dev**: static hostPath PV (path set by `sharedWorkspace.hostPath` in platform values-dev.yaml) + `storageClassName: manual`. K3s's bundled `local-path` provisioner hard-codes RWO, so we bypass it with a pre-declared PV that advertises RWX. Single-node K3s handles multi-pod RWX access fine.
- **Prod**: dynamic provisioning via EFS (`storageClassName: efs-sc`). No static PV needed — the CSI driver creates one on PVC bind.

`charts/aviary-environment` has no PVC template; the Deployment references `.Values.pvc.claimName` (default `aviary-shared-workspace`).

### React Strict Mode
Use `useRef` guards for WebSocket connections and OIDC callbacks to prevent duplicate execution in dev mode.

## Access Model

**Owner-only, full stop.** Agents, sessions, and workflows are visible and mutable only to the user whose `id` matches `owner_id` / `created_by`. There are no teams, no visibility levels, no platform admins, no invited participants. This is a deliberate simplification ahead of an RBAC redesign — when RBAC returns we'll introduce it as a first-class layer rather than patches on top of the old ACL tables.

## Testing

```bash
# API server tests (services compose)
cd services && docker compose exec api pytest tests/ -v

# Admin console tests
cd services && docker compose exec admin pytest tests/ -v

# Supervisor tests (requires Redis env var)
cd agent-supervisor && uv run pytest tests/ -v
```

API/Admin: dedicated `aviary_test` database with `NullPool`, no lifespan.

## Rebuilding Images / Applying Chart Changes

**Runtime image** (K3s) — after modifying [runtime/](runtime/):

```bash
./scripts/quick-rebuild.sh runtime    # build + ctr import + rolling restart agent pods
```

**Supervisor** — after modifying [agent-supervisor/](agent-supervisor/):

```bash
./scripts/quick-rebuild.sh agent-supervisor    # docker compose up -d --build supervisor
```

**Helm chart changes** — render locally and apply via K3s kubectl. Brings up the K3s container if it isn't already running:

```bash
./scripts/chart-test.sh             # build runtime images + helm apply all 3 charts (full flow)
./scripts/helm-apply.sh platform    # apply a single chart (K3s already running)
./scripts/helm-apply.sh default
./scripts/helm-apply.sh custom
```

[scripts/chart-test.sh](scripts/chart-test.sh) renders `alpine/helm:3.14.4 template` with `hostGatewayIP` from the K3s container and pipes into `kubectl apply -f -`.

**Hot reload** for project-root services — bind-mount + `--reload` / `npm run dev` from [compose.override.yml](compose.override.yml). Tweaking local-infra config (LiteLLM patches, prometheus.yml, etc.) needs `cd local-infra && docker compose restart <svc>`.

## Key Environment Variables (API)

| Variable | Purpose |
|----------|---------|
| `OIDC_ISSUER` | Public IdP URL (token `iss` validation). Unset → no-IdP mode (single dev user). |
| `OIDC_INTERNAL_ISSUER` | Internal IdP URL (discovery/JWKS fetch) — leave empty for hosted IdPs |
| `OIDC_CLIENT_ID` | OIDC client id used for the auth-code/PKCE flow |
| `OIDC_CLIENT_SECRET` | Required for confidential clients (e.g. Okta); leave unset for PKCE-only public clients |
| `OIDC_AUDIENCE` | Optional `aud` claim check |
| `DEV_USER_SUB` | `sub` used everywhere when `OIDC_ISSUER` is unset (default: `dev-user`) |
| `DATABASE_URL` | PostgreSQL async connection |
| `REDIS_URL` | Redis for pub/sub, caching, presence |
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
| `LITELLM_URL` | LiteLLM gateway URL (`http://litellm.platform.svc:4000`) — serves inference + aggregated MCP at `/mcp` |
| `LITELLM_API_KEY` | LiteLLM master key (`sk-aviary-dev`) |
| `AVIARY_API_URL` | Service URL for runtime-side tools |

## Key Environment Variables (Agent Supervisor)

| Variable | Purpose |
|----------|---------|
| `REDIS_URL` | Redis DSN for publishing agent stream events (default: `redis://redis:6379/0`) |
| `SUPERVISOR_DEFAULT_RUNTIME_ENDPOINT` | Fallback endpoint used when a caller passes `runtime_endpoint=null` |
| `METRICS_ENABLED` | Toggle Prometheus `/metrics` (default: true) |
| `OIDC_ISSUER` | Public IdP URL (Bearer token `iss` validation on `/publish` and `/a2a`). Unset → no-IdP mode. |
| `OIDC_INTERNAL_ISSUER` | Internal IdP URL (JWKS fetch) — leave empty for hosted IdPs |
| `OIDC_AUDIENCE` | Optional `aud` claim check |
| `DEV_USER_SUB` | `sub` used when `OIDC_ISSUER` is unset (default: `dev-user`) |
| `VAULT_ADDR` / `VAULT_TOKEN` | Vault connection for per-user credential lookup (keyed by JWT `sub`) |

## Key Environment Variables (LiteLLM Gateway)

| Variable | Purpose |
|----------|---------|
| `LITELLM_MASTER_KEY` | LiteLLM proxy auth key (default: `sk-aviary-dev`) |
| `VAULT_ADDR` / `VAULT_TOKEN` | Vault connection for per-user API key + MCP credential lookup |
| `OIDC_ISSUER` | Public IdP URL (JWT `iss` validation for inference hook + MCP guardrail). Unset → no-IdP mode (every caller is `DEV_USER_SUB`). |
| `OIDC_INTERNAL_ISSUER` | Internal IdP URL (JWKS fetch) |
| `DEV_USER_SUB` | `sub` used when `OIDC_ISSUER` is unset (default: `dev-user`) |
| `MCP_TOOL_PREFIX_SEPARATOR` | Set to `__` so MCP tools are exposed as `{server}__{tool}` (matches `mcp_agent_tool_bindings` naming) |
| `AVIARY_MCP_INJECTION_CONFIG` | Path to the per-server Vault-arg injection YAML (default `/app/aviary-mcp-secret-injection.yaml`) |

### MCP Aggregation (via LiteLLM)

LiteLLM is the **single source of truth** for the MCP catalog. It exposes `/mcp` as an aggregated Streamable-HTTP endpoint that fans out to every registered backend MCP server. Every ACL decision on servers and tools belongs to LiteLLM; Aviary only stores per-agent tool bindings.

**Catalog storage — two sources, both owned by LiteLLM:**
- **YAML** (`config/litellm/config.yaml` → `mcp_servers:`): platform servers declared at deploy time (e.g. jira, confluence with `allow_all_keys: true`).
- **Prisma DB** (`LiteLLM_MCPServerTable`): dynamic servers added at runtime via LiteLLM's own UI or API. Aviary has no admin-side CRUD for MCP servers — LiteLLM is the sole management surface.

**Aviary DB — only bindings:**
- `mcp_agent_tool_bindings (agent_id, server_name, tool_name)` — the tools the owner selected for this agent, referenced by the stable LiteLLM-side names (no FK to a mirrored server table).

**Visibility model (today — binary):**
- Public servers (`allow_all_keys: true`) — LiteLLM exposes them to every caller with a valid Bearer.
- Private servers (`allow_all_keys: false`) — LiteLLM hides them from raw-JWT callers; admin sees everything via the master key.
- Future RBAC (e.g. per-user grants, team scopes) plugs into `_rbac_filter_tools()` inside [aviary_mcp_credentials.py](config/litellm/patches/aviary_mcp_credentials.py) — no Aviary-side ACL table.

**Authentication (per-hook JWT enforcement — LiteLLM OSS native JWT auth is Enterprise-gated and `/mcp` fails open under OAuth2 passthrough, so the guardrail validates at every entry point):**
- **Request ingress gate** — monkey-patches `MCPRequestHandler.process_mcp_request` so invalid/tampered/expired JWTs raise 401 before any handler runs. Master keys (`sk-*`) fall through.
- **`tools/list`** — validates the bearer, runs the RBAC stub, strips Vault-injected parameters from `inputSchema`, then applies the per-agent `X-Aviary-Allowed-Tools` filter (header forwarded by the runtime).
- **`tools/call`** — validates the bearer, gates on `X-Aviary-Allowed-Tools`, then the `pre_mcp_call` hook fetches per-user secrets from Vault (`secret/aviary/credentials/{sub}/{vault_key}`, per-server map in `config/litellm/mcp-secret-injection.yaml`) and injects them as `modified_arguments`. The user token is **never** forwarded to backend MCP servers.

**Tool namespacing:** LiteLLM prefixes with `MCP_TOOL_PREFIX_SEPARATOR=__` → `{server}__{tool}`. Claude Code wraps that as `mcp__gateway__{server}__{tool}` (`gateway` is the fixed `mcpServers` key in `runtime/src/agent.ts`).

**Data flow — chat message:**
1. API reads `mcp_agent_tool_bindings` for the agent and merges them into `agent_config.tools` as `mcp__gateway__{server}__{tool}`.
2. Supervisor forwards to the runtime; runtime opens `mcpServers.gateway` → `${LITELLM_URL}/mcp` with `Authorization: Bearer <user JWT>` + `X-Aviary-Allowed-Tools: {server}__{tool},…`.
3. Claude Code's MCP client requests `tools/list`; LiteLLM guardrail validates JWT → strips injected args → filters to the allow-list → returns.
4. On `tools/call`: guardrail validates JWT → allow-list gate → Vault injection → forwards to the backend MCP server (e.g. `mcp-jira`).

**Data flow — user browsing the catalog:**
1. Frontend hits `GET /api/mcp/servers` (or `/tools`, `/tools/search`).
2. API opens a short-lived MCP session to `${LITELLM_URL}/mcp` with the user's JWT and returns whatever LiteLLM aggregates. No Aviary-side filtering.
3. On `PUT /api/mcp/agents/{id}/tools` the API validates each requested tool against the same LiteLLM view before persisting to `mcp_agent_tool_bindings` (can't bind what the user can't see).

**Architecture principle:** Aviary never judges who can see what MCP resource — it forwards the user token to LiteLLM and trusts the answer. RBAC is LiteLLM's concern.
