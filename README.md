# Aviary

**Multi-Tenant AI Agent Platform**

[한국어](./README.ko.md)

Aviary is an enterprise platform where users can create, configure, and use purpose-built AI agents through a web UI. Each agent runs in an isolated Kubernetes namespace with long-running Pods that serve multiple sessions concurrently, isolated at the kernel level via bubblewrap sandboxing.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Web UI (Next.js)                        │
│    Agent Catalog · Create/Edit · Chat Sessions · ACL Settings  │
└───────────────┬────────────────────────────────────────────────┘
                │ REST + WebSocket
┌───────────────▼────────────────────────────────────────────────┐
│                     API Server (FastAPI)                        │
│       OIDC Auth · Agent CRUD · Session Mgr · ACL · A2A         │
└───┬───────────┬───────────┬────────────────────────────────────┘
    │           │           │
    │           │           │           ┌────────────────────────┐
    │           │           │           │  Admin Console         │
    │           │           │           │  Policy · Scaling ·    │
    │           │           │           │  Deployments · Web UI  │
    │           │           │           └───────────┬────────────┘
    │           │           │                       │
    │           │   ┌───────▼────────────────────────────────────┐
    │           │   │           Platform Services                │
    │           │   │                                            │
    │           │   │  ┌─────────────────┐                       │
    │           │   │  │ LiteLLM Gateway │◀── Vault              │
    │           │   │  │ (model routing, │    (per-user API keys)│
    │           │   │  │  API key inject)│                       │
    │           │   │  └────────┬────────┘                       │
    │           │   │  ┌────────▼────────┐                       │
    │           │   │  │ Portkey Gateway │                       │
    │           │   │  │ (guardrails,    │                       │
    │           │   │  │  tracing, cache)│                       │
    │           │   │  └────────┬────────┘                       │
    │           │   │     ┌─────┴───────────────────┐            │
    │           │   │     ▼            ▼            ▼            │
    │           │   │  Claude API   Ollama/vLLM   Bedrock        │
    │           │   │                                            │
    │           │   │  ┌─────────────────────────────────────┐   │
    │           │   │  │ MCP Gateway                         │◀─ Vault
    │           │   │  │ (tool catalog, ACL, proxy,          │   (tool creds)
    │           │   │  │  OIDC auth, auto-discovery)         │   │
    │           │   │  └────────┬────────────────────────────┘   │
    │           │   │           ▼                                 │
    │           │   │     Backend MCP Servers                     │
    │           │   └────────────────────────────────────────────┘
    │           │
    │   ┌───────▼────────────────────────────────────────────────┐
    │   │                   Kubernetes Cluster                    │
    │   │                                                        │
    │   │  ┌─── NS: platform ──────────────────────────────────┐ │
    │   │  │  ┌─────────────────┐  ┌────────────────────────┐  │ │
    │   │  │  │  Egress Proxy   │  │  Agent Supervisor      │  │ │
    │   │  │  │  (forward proxy │  │  (K8s lifecycle,       │  │ │
    │   │  │  │   + allowlist)  │  │   auto-scaling,        │  │ │
    │   │  │  │                 │  │   idle cleanup)        │  │ │
    │   │  │  └────────┬────────┘  └────────────────────────┘  │ │
    │   │  │           ▼                                        │ │
    │   │  │     External APIs (GitHub, S3, ...)                │ │
    │   │  └────────────────────────────────────────────────────┘ │
    │   │                                                        │
    │   │  ┌─── NS: agent-{id} ──────────────────────────────┐   │
    │   │  │  Agent Pod (1-N replicas)                        │   │
    │   │  │  claude-agent-sdk + Claude Code CLI + Python     │   │
    │   │  │  bwrap sandbox · shared home · per-agent .claude │   │
    │   │  │                                                  │   │
    │   │  │  LLM ──▶ LiteLLM    NetworkPolicy:              │   │
    │   │  │  Tools ▶ MCP GW     deny-by-default             │   │
    │   │  │  HTTP ──▶ Egress    A2A ──▶ API Server           │   │
    │   │  └──────────────────────────────────────────────────┘   │
    │   └────────────────────────────────────────────────────────┘
    │
    └─▶ PostgreSQL · Redis · Keycloak · Vault
```

## Key Features

- **Agent-per-Pod with Multi-Session** — Each agent gets a long-running Deployment (1-N replicas) serving multiple sessions concurrently, auto-scaled based on session load
- **Bubblewrap Session Isolation** — Each session runs in a kernel-level mount namespace; agents in the same session share a workspace directory for file exchange, while each agent's `.claude/` context is isolated via PVC overlay
- **Agent-to-Agent (A2A)** — Agents invoke other agents via `@mention` in instructions or chat messages; sub-agent tool calls render inline under the parent tool card in real-time
- **MCP Gateway** — Centralized tool management via [Model Context Protocol](https://modelcontextprotocol.io/); admin registers MCP servers, tools are auto-discovered, users bind tools to agents with per-user ACL (default-deny)
- **LiteLLM + Portkey Gateway** — Two-layer LLM gateway: [LiteLLM](https://github.com/BerriAI/litellm) for model routing and per-user API key injection, [Portkey](https://github.com/portkey-ai/gateway) for guardrails, tracing, and caching
- **Multi-Backend Inference** — Claude API, Ollama, vLLM, AWS Bedrock; add new backends via config
- **Egress Control** — Deny-by-default outbound proxy with per-agent allowlists (CIDR, domain, wildcard); changes apply immediately
- **Live Config** — Agent instruction and tools update from DB on every message turn, no Pod restarts
- **OIDC + ACL** — Keycloak/Okta auth with team sync; role hierarchy (`viewer` < `user` < `admin` < `owner`)
- **Vault Secrets** — Per-user API keys and tool credentials injected at gateway level, never exposed to Pods

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web UI | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui |
| API Server | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Agent Runtime | Node.js, Python, claude-agent-sdk, Claude Code CLI |
| LLM Gateway | [LiteLLM](https://github.com/BerriAI/litellm) + [Portkey](https://github.com/portkey-ai/gateway) |
| MCP Gateway | Python, FastAPI, [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) |
| Infrastructure | PostgreSQL, Redis, Keycloak, Vault, Kubernetes (K3s for dev) |

## Project Structure

```
aviary/
├── api/                  # API Server — user-facing REST + WebSocket + A2A
├── admin/                # Admin Console — operator-facing web UI
├── web/                  # Web UI (Next.js)
├── runtime/              # Agent Runtime (runs in K8s agent Pods)
├── shared/               # Shared package (OIDC, ACL, DB models)
├── mcp-gateway/          # MCP tool catalog, ACL, and proxy
├── agent-supervisor/     # K8s lifecycle manager (runs in K8s)
├── mcp-servers/          # Platform-provided MCP server stubs
├── k8s/                  # K8s manifests
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

This single command builds all images, starts all services, runs DB migrations, and provisions the K8s cluster.

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API Server | http://localhost:8000 |
| Admin Console | http://localhost:8001 |
| Keycloak Admin | http://localhost:8080 |

Test accounts: `user1@test.com` / `user2@test.com` (password: `password`)

```bash
docker compose up -d          # Start
docker compose down           # Stop (data preserved)
docker compose down -v        # Full reset
```

Source code is bind-mounted — edits to `api/` and `web/` are reflected via hot reload.

## Testing

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
```

## Key Design Decisions

### LiteLLM + Portkey Gateway
Agent Pods never call LLM backends directly. [LiteLLM](https://github.com/BerriAI/litellm) routes requests by model name prefix to the appropriate backend, then [Portkey AI Gateway](https://github.com/portkey-ai/gateway) provides guardrails, tracing, logging, and caching. LiteLLM natively supports the Anthropic Messages API, so claude-agent-sdk works transparently. This centralizes credentials, rate limiting, and observability.

### MCP Gateway
Agent tool calls are routed through a centralized [MCP](https://modelcontextprotocol.io/) Gateway. Operators register backend MCP servers via the Admin Console, and tools are auto-discovered. Users browse an ACL-filtered catalog and bind tools to agents. The user's OIDC token is propagated end-to-end for permission validation and never forwarded to external services.

### Agent-to-Agent (A2A)
Agents can call other agents as sub-agents via `@mention`. The runtime exposes a per-message HTTP MCP server with one tool per accessible agent. Calls route through the API server for auth and ACL. Sub-agent tool calls are published to the parent session's Redis channel and rendered inline. All agents in a session share the same home directory via hostPath volumes.

### Session Isolation
The Claude CLI runs inside a bubblewrap mount namespace. All agents in a session share `/workspace` via hostPath for file exchange. Each agent's `.claude/` is isolated via PVC overlay so conversation histories stay independent. Other sessions are invisible at the namespace level.

### ACL Resolution
Permission follows 6 steps: agent owner → direct user ACL → team ACL → public visibility → team visibility → deny. Roles: `viewer` < `user` < `admin` < `owner`.
