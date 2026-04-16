# Aviary

**Multi-Tenant AI Agent Platform**

[한국어](./README.ko.md)

Aviary is an enterprise platform where users create, configure, and chat with purpose-built AI agents through a web UI. Runtime environments are pre-provisioned as Helm releases (one Deployment pool per environment); every agent shares the pool, isolated at the kernel level via bubblewrap and at the network level via a baseline NetworkPolicy plus optional per-environment rules.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Web UI (Next.js)                        │
│    Agent Catalog · Create/Edit · Chat Sessions · ACL Settings  │
└───────────────┬────────────────────────────────────────────────┘
                │ REST + WebSocket
┌───────────────▼────────────────────────────────────────────────┐
│                     API Server (FastAPI)                        │
│   OIDC Auth · Agent CRUD · Session Mgr · ACL · A2A              │
│   (reads agent.runtime_endpoint, forwards to supervisor)        │
└───┬───────────┬────────────────────────────────────────────────┘
    │           │                           ┌────────────────────┐
    │           │                           │  Admin Console     │
    │           │                           │  Agent config +    │
    │           │                           │  runtime_endpoint  │
    │           │                           │  override          │
    │           │                           └──────────┬─────────┘
    │   ┌───────▼────────────────────────────────────┐ │
    │   │            Platform Services              │ │
    │   │                                            │ │
    │   │  ┌─────────────────┐                       │ │
    │   │  │ LiteLLM Gateway │◀── Vault              │ │
    │   │  │ (model routing, │    (per-user keys)    │ │
    │   │  │  API key inject)│                       │ │
    │   │  └────────┬────────┘                       │ │
    │   │  ┌────────▼────────┐                       │ │
    │   │  │ Portkey Gateway │                       │ │
    │   │  │ (guardrails,    │                       │ │
    │   │  │  tracing, cache)│                       │ │
    │   │  └────────┬────────┘                       │ │
    │   │     ┌─────┴───────────────────┐            │ │
    │   │     ▼            ▼            ▼            │ │
    │   │  Claude API   Ollama/vLLM   Bedrock        │ │
    │   │                                            │ │
    │   │  ┌─────────────────────────────────────┐   │ │
    │   │  │ MCP Gateway                         │◀──┴ Vault
    │   │  │ (tool catalog, ACL, proxy,          │     (tool creds)
    │   │  │  OIDC auth, auto-discovery)         │     │
    │   │  └────────┬────────────────────────────┘     │
    │   │           ▼                                   │
    │   │     Backend MCP Servers                       │
    │   └──────────────────────────────────────────────┘
    │
    │   ┌────────────────────────────────────────────────────────┐
    │   │                   Kubernetes Cluster                    │
    │   │          (local: K3s · prod: EKS, via Helm)             │
    │   │                                                        │
    │   │  ┌─── NS: platform ──────────────────────────────────┐ │
    │   │  │ Agent Supervisor (stateless)                      │ │
    │   │  │   SSE proxy · Redis publish · /metrics            │ │
    │   │  │   (caller injects runtime_endpoint in each req)   │ │
    │   │  └────────────────────────────────────────────────────┘ │
    │   │                                                        │
    │   │  ┌─── NS: agents ────────────────────────────────────┐  │
    │   │  │ baseline NetworkPolicy (DNS + platform +          │  │
    │   │  │   LiteLLM + MCP GW + API)                         │  │
    │   │  │                                                   │  │
    │   │  │ Env release: aviary-env-default                   │  │
    │   │  │   Deployment (replicas ≥ 1) · Service · RWX PVC   │  │
    │   │  │   runtime pool serves every agent                 │  │
    │   │  │   bwrap sandbox · shared session dir ·            │  │
    │   │  │   per-(agent,session) .claude and .venv           │  │
    │   │  │                                                   │  │
    │   │  │ Env release: aviary-env-custom-* (optional)       │  │
    │   │  │   Same shape, independent pool + extraEgress      │  │
    │   │  └───────────────────────────────────────────────────┘  │
    │   └─────────────────────────────────────────────────────────┘
    │
    └─▶ PostgreSQL · Redis · Keycloak · Vault
```

## Key Features

- **Pre-Provisioned Runtime Environments** — Helm releases of `charts/aviary-environment` stand up the runtime pool declaratively; no per-agent Deployments, no cold starts. Environments are always on.
- **Stateless Reverse SSE Proxy** — Agent Supervisor has zero infra responsibilities: every caller (API, future Temporal worker, batch jobs) passes `runtime_endpoint` in the request body, the supervisor forwards SSE, publishes to Redis, assembles the final message, and emits Prometheus metrics.
- **Per-Agent Endpoint Override** — Agents share the default environment by default; the Admin Console sets `runtime_endpoint` on an agent to route it to a dedicated custom environment (e.g. a GPU pool, isolated SG) — no code change needed, no DB migration.
- **Agent-Agnostic Runtime Pool** — Every pod in an environment serves every agent; `agent_id` arrives per-request in `agent_config`. Isolation comes from on-disk paths (`sessions/{sid}/agents/{aid}/…`) plus bubblewrap, not per-agent pods.
- **Bubblewrap Session Isolation** — Each request runs inside a kernel-level mount namespace; agents in the same session share `/workspace` for file exchange (A2A), while `.claude/` and `.venv/` are per-(agent, session).
- **Agent-to-Agent (A2A)** — Agents invoke other agents via `@mention` in instructions or chat messages; sub-agent tool calls render inline under the parent tool card in real-time.
- **MCP Gateway** — Centralized tool management via [Model Context Protocol](https://modelcontextprotocol.io/); admins register MCP servers, tools are auto-discovered, users bind tools to agents with per-user ACL (default-deny).
- **LiteLLM + Portkey Gateway** — Two-layer LLM gateway: [LiteLLM](https://github.com/BerriAI/litellm) for model routing and per-user API-key injection, [Portkey](https://github.com/portkey-ai/gateway) for guardrails, tracing, and caching.
- **Multi-Backend Inference** — Claude API, Ollama, vLLM, AWS Bedrock; add new backends via config.
- **Layered Egress** — Baseline NetworkPolicy from `charts/aviary-platform` is always in effect; per-environment `extraEgress` in Helm values adds additional rules (K8s NP evaluates as a disjunction).
- **Redis-Decoupled Streaming** — Supervisor consumes runtime SSE and publishes to Redis; API server saves the assembled message and WebSocket clients replay from the same Redis stream independently.
- **Live Config** — Agent instruction, tools, and MCP server bindings update from DB on every message turn — no Pod restarts.
- **OIDC + ACL** — Keycloak/Okta auth with team sync; role hierarchy (`viewer` < `user` < `admin` < `owner`).
- **Vault Secrets** — Per-user API keys and tool credentials injected at gateway level, never exposed to Pods.
- **Local K3s / Prod EKS** — Same Helm charts on both. Dev uses a hostPath PVC on the K3s node; prod flips a single values file to EFS RWX.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web UI | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui |
| API Server | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Agent Runtime | Node.js, Python, claude-agent-sdk, Claude Code CLI |
| Agent Supervisor | Python, FastAPI, Redis, prometheus-client |
| LLM Gateway | [LiteLLM](https://github.com/BerriAI/litellm) + [Portkey](https://github.com/portkey-ai/gateway) |
| MCP Gateway | Python, FastAPI, [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) |
| Deployment | Helm charts (`charts/aviary-platform`, `charts/aviary-environment`) |
| Infrastructure | PostgreSQL, Redis, Keycloak, Vault, Kubernetes (K3s for dev, EKS for prod) |

## Project Structure

```
aviary/
├── api/                  # API Server — user-facing REST + WebSocket + A2A
├── admin/                # Admin Console — operator-facing web UI (config + endpoint override)
├── web/                  # Web UI (Next.js)
├── runtime/              # Agent Runtime — agent-agnostic pool member
├── shared/               # Shared package (OIDC, ACL, DB models)
├── mcp-gateway/          # MCP tool catalog, ACL, and proxy
├── agent-supervisor/     # Stateless SSE proxy + Redis publisher + /metrics
├── mcp-servers/          # Platform-provided MCP server stubs
├── charts/
│   ├── aviary-platform/      # Namespaces, supervisor, baseline egress, etc.
│   └── aviary-environment/   # One runtime environment (Deployment + Service + PVC + NP)
├── config/               # LiteLLM, Keycloak, K3s config
├── scripts/              # Dev setup and utilities
└── docker-compose.yml
```

## Getting Started

**Prerequisites:** Docker Desktop (or equivalent container runtime)

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh
```

This single command builds all images, starts all services, runs DB migrations, and installs the Helm charts (`aviary-platform` + default `aviary-env-default`).

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API Server | http://localhost:8000 |
| Admin Console | http://localhost:8001 |
| Supervisor Metrics | http://localhost:9000/metrics |
| Keycloak Admin | http://localhost:8080 |

Test accounts: `user1@test.com` / `user2@test.com` (password: `password`)

```bash
docker compose up -d          # Start
docker compose down           # Stop (data preserved)
docker compose down -v        # Full reset
```

Source code is bind-mounted — edits to `api/`, `admin/`, and `web/` hot-reload.

### Adding a custom environment

```bash
docker run --rm -v "$PWD/charts:/charts:ro" alpine/helm:3.14.4 template \
  aviary-env-gpu /charts/aviary-environment \
  --set name=gpu --set replicas=2 --set extraEgress='[...rules...]' \
  | docker compose exec -T k8s kubectl apply -f -
```

Then, in Admin Console → agent detail, set the **Runtime Endpoint Override** to
`http://aviary-env-gpu.agents.svc:3000`. Next chat message routes to the new pool.

## Testing

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
cd agent-supervisor && uv run pytest tests/ -v
```

## Key Design Decisions

### Stateless Supervisor, Endpoint Injection
The supervisor owns no DB connection and no K8s API access. Every caller (today the API server; tomorrow a Temporal worker or batch job) looks up `agent.runtime_endpoint` and passes it in the publish request body. Null falls back to a Helm-configured default environment. This keeps the supervisor reusable across orchestration paths without code changes.

### Helm-Declared Environments
Runtime infrastructure lives entirely in `charts/aviary-environment`. Spinning up a new environment = `helm template | kubectl apply`. Local dev differs from production only in a values file (hostPath vs. EFS, NodePort vs. LoadBalancer). There are no dynamic K8s operations in application code.

### LiteLLM + Portkey Gateway
Agent Pods never call LLM backends directly. [LiteLLM](https://github.com/BerriAI/litellm) routes by model name prefix, [Portkey](https://github.com/portkey-ai/gateway) layers guardrails, tracing, logging, and caching on top. LiteLLM natively supports the Anthropic Messages API, so claude-agent-sdk works transparently.

### MCP Gateway
Agent tool calls are routed through a centralized [MCP](https://modelcontextprotocol.io/) Gateway. Admins register backend MCP servers via the Admin Console, tools auto-discover, and users bind ACL-filtered tools to agents. The user's OIDC token is propagated end-to-end and never forwarded to external services.

### Agent-to-Agent (A2A)
Agents call other agents as sub-agents via `@mention`. The runtime exposes a per-message HTTP MCP server with one tool per accessible agent. A2A calls route through the API for auth + ACL. Sub-agent tool calls publish to the parent session's Redis channel and render inline. Agents in the same session share `/workspace` via the environment's RWX PVC.

### Session Isolation
Claude CLI runs inside a bubblewrap mount namespace. The environment PVC is structured as `/workspace-root/sessions/{sid}/shared/` (cross-agent session area) and `/workspace-root/sessions/{sid}/agents/{aid}/{.claude,.venv}/` (per-(agent, session) overlays). bwrap rewrites these onto `/workspace`, `/workspace/.claude`, `/workspace/.venv` so the sandbox view is identical regardless of pool member.

### ACL Resolution
Permission follows 6 steps: agent owner → direct user ACL → team ACL → public visibility → team visibility → deny. Roles: `viewer` < `user` < `admin` < `owner`.
