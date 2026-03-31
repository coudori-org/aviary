# Aviary

**Multi-Tenant AI Agent Platform**

[한국어](./README.ko.md)

Aviary is an enterprise platform where users can create, configure, deploy, and use purpose-built AI agents through a web UI. Each agent runs in an isolated Kubernetes namespace with long-running Pods that serve multiple sessions concurrently, isolated at the kernel level via bubblewrap sandboxing.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Web UI (Next.js 15)                     │
│    Agent Catalog · Create/Edit · Chat Sessions · ACL Settings  │
└───────────────┬────────────────────────────────────────────────┘
                │ REST + WebSocket
┌───────────────▼────────────────────────────────────────────────┐
│                     API Server (FastAPI)                        │
│    OIDC Auth · Agent CRUD · Session Mgr · ACL · Vault Client   │
└───┬───────────┬────────────────────────────────────────────────┘
    │           │ K8s API Proxy
    │   ┌───────▼────────────────────────────────────────────────┐
    │   │                 Kubernetes Cluster                      │
    │   │                                                        │
    │   │  ┌─── NS: platform ──────────────────────────────────┐ │
    │   │  │                                                    │ │
    │   │  │  ┌─────────────────┐  ┌──────────────────┐        │ │
    │   │  │  │ Inference Router │  │ Credential Proxy │        │ │
    │   │  │  │ (LLM gateway)   │  │ (Vault secrets)  │        │ │
    │   │  │  └────────┬────────┘  └──────────────────┘        │ │
    │   │  │           │                                        │ │
    │   │  │     ┌─────┴───────────────────┐                    │ │
    │   │  │     ▼            ▼            ▼                    │ │
    │   │  │  Claude API   Ollama/vLLM   Bedrock                │ │
    │   │  │                                                    │ │
    │   │  │  ┌─────────────────┐  ┌──────────────────┐        │ │
    │   │  │  │  Egress Proxy   │  │  Image Warmer    │        │ │
    │   │  │  │  (HTTP/HTTPS    │  │  (DaemonSet)     │        │ │
    │   │  │  │   forward proxy │  └──────────────────┘        │ │
    │   │  │  │   + policy      │                               │ │
    │   │  │  │   enforcement)  │                               │ │
    │   │  │  └────────┬────────┘                               │ │
    │   │  │           │ per-agent allowlist                     │ │
    │   │  │           ▼                                        │ │
    │   │  │     External APIs (GitHub, S3, ...)                │ │
    │   │  └────────────────────────────────────────────────────┘ │
    │   │                                                        │
    │   │  ┌─── NS: agent-{id} ──────┐  ┌── NS: agent-{id} ──┐ │
    │   │  │  Agent Pod (1-N)         │  │  Agent Pod (1-N)    │ │
    │   │  │  claude-agent-sdk        │  │  claude-agent-sdk   │ │
    │   │  │  + Claude Code CLI       │  │  + Claude Code CLI  │ │
    │   │  │  + bwrap sandbox         │  │  + bwrap sandbox    │ │
    │   │  │  PVC: /workspace         │  │  PVC: /workspace    │ │
    │   │  │                          │  │                     │ │
    │   │  │  HTTP_PROXY ─────────────┼──┼──▶ Egress Proxy     │ │
    │   │  │  NetworkPolicy: deny all │  │  NetworkPolicy:     │ │
    │   │  │    except platform NS    │  │    deny all except  │ │
    │   │  │    + allowed CIDRs       │  │    platform NS      │ │
    │   │  └──────────────────────────┘  └─────────────────────┘ │
    │   └────────────────────────────────────────────────────────┘
    │
    │  ┌───────────────┐  ┌──────────────┐  ┌────────────────┐
    └─▶│  PostgreSQL    │  │    Redis      │  │   Keycloak     │
       │  DB, sessions  │  │  pub/sub,     │  │   OIDC auth    │
       │  ACL, agents   │  │  egress rules │  │   team sync    │
       └───────────────┘  └──────────────┘  └────────────────┘
```

## Key Features

- **Agent-per-Pod with Multi-Session** — Each agent gets a long-running Deployment (1-N replicas) serving multiple sessions concurrently, auto-scaled based on session load
- **Bubblewrap Session Isolation** — Each session runs inside a bwrap mount namespace; other sessions' files are invisible at the kernel level
- **Namespace-per-Agent** — NetworkPolicy, ResourceQuota, and ServiceAccount scoped per agent
- **Egress Proxy** — All outbound HTTP/HTTPS from agent Pods routed through a centralized proxy with per-agent allowlists (CIDR, exact domain, wildcard `*.example.com`); deny-by-default, policy changes take effect immediately without Pod restarts
- **claude-agent-sdk Powered** — Full [Claude Code](https://docs.anthropic.com/en/docs/claude-code) harness via `ClaudeSDKClient` including tools, sub-agents, MCP servers, file I/O, and shell execution
- **Inference Router** — Centralized LLM gateway; model name determines backend routing transparently
- **Multi-Backend Inference** — Claude API, Ollama, vLLM, AWS Bedrock; new backends require no NetworkPolicy changes
- **Live Config Updates** — Agent config (instruction, tools) is passed from DB on every message; edits take effect immediately without Pod restarts
- **OIDC Auth + Team Sync** — Keycloak (dev) / Okta (prod); IdP groups auto-sync to Aviary teams on login
- **Granular ACL** — 7-step permission resolution with role hierarchy (`viewer` < `user` < `admin` < `owner`)
- **Credential Proxy** — Secrets never enter session Pods; injected from Vault via a shared proxy
- **Real-time Chat** — WebSocket streaming with Redis pub/sub for multi-user shared sessions

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web UI | Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| API Server | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Agent Runtime | Python 3.12, claude-agent-sdk, Claude Code CLI, Node.js 22 |
| Inference Router | Python 3.12, FastAPI — Anthropic Messages API proxy |
| Egress Proxy | Python 3.12, asyncio — HTTP/HTTPS forward proxy with policy enforcement |
| Database | PostgreSQL 16 |
| Cache / PubSub | Redis 7 |
| Auth | Keycloak 25 (dev) / Okta (prod) — OIDC |
| Secrets | HashiCorp Vault |
| Orchestration | Kubernetes (K3s for local dev) |
| Inference Backends | Claude API, Ollama, vLLM, AWS Bedrock |

## Project Structure

```
aviary/
├── api/                     # API Server (FastAPI)
│   ├── app/
│   │   ├── auth/            # OIDC validation, team sync
│   │   ├── db/              # SQLAlchemy models, Alembic migrations
│   │   ├── routers/         # REST + WebSocket endpoints
│   │   ├── services/        # Business logic (agent, session, k8s, vault, acl, redis)
│   │   └── schemas/         # Pydantic models
│   └── tests/               # pytest (16 tests)
├── web/                     # Web UI (Next.js 15)
│   └── src/
│       ├── app/             # Pages (agents, sessions, login)
│       ├── components/      # Chat, agent management, UI primitives
│       └── lib/             # API client, auth, WebSocket
├── runtime/                 # Agent Runtime (runs in agent Pods)
│   └── app/                 # claude-agent-sdk harness, session manager
├── inference-router/        # LLM Gateway (platform namespace)
│   └── app/                 # Anthropic API proxy, backend routing
├── credential-proxy/        # Secret injection proxy (platform namespace)
│   └── app/                 # Vault client, session resolver
├── egress-proxy/            # HTTP/HTTPS egress proxy (platform namespace)
│   └── app/                 # Forward proxy, per-agent policy checker
├── config/                  # Keycloak realm, K3s config
├── k8s/platform/            # K8s manifests
├── scripts/                 # Dev setup, DB init, seeding
└── docker-compose.yml       # Full dev environment
```

## Getting Started

### Prerequisites

- Docker Desktop (or equivalent container runtime)

### Quick Start

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh
```

This single command builds all images, starts all services (API, Web, PostgreSQL, Redis, Keycloak, Vault, K3s), runs DB migrations, and loads runtime images into K3s.

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API Server | http://localhost:8000 |
| Keycloak Admin | http://localhost:8080 (admin/admin) |
| Vault | http://localhost:8200 |

### Test Accounts

| Email | Password | Role | Teams |
|-------|----------|------|-------|
| admin@test.com | password | Platform Admin | engineering |
| user1@test.com | password | Regular User | engineering, product |
| user2@test.com | password | Regular User | data-science |

### Everyday Commands

```bash
docker compose up -d          # Start
docker compose down           # Stop (data preserved)
docker compose down -v        # Stop + delete all data
docker compose logs -f api    # Tail logs
```

### Development

Source code is bind-mounted into containers. Edits to `api/` and `web/` are reflected automatically via uvicorn `--reload` and Next.js HMR.

```bash
# Rebuild after dependency changes
docker compose up -d --build api
docker compose up -d --build web

# Rebuild K3s images (runs inside K3s)
docker build -t aviary-runtime:latest ./runtime/
docker build -t aviary-egress-proxy:latest ./egress-proxy/
docker save aviary-runtime:latest aviary-egress-proxy:latest | docker compose exec -T k3s ctr images import -
```

## Testing

```bash
docker compose exec api pytest tests/ -v
```

16 tests covering health, agent CRUD, ACL (visibility, grants, permission deny), and sessions (create, list, access control, archive). Uses a dedicated `aviary_test` database and token-based mock auth for multi-user scenarios.

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/config` | OIDC provider configuration |
| POST | `/api/auth/callback` | Exchange auth code for tokens |
| GET | `/api/auth/me` | Current user info |

### Agents
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/agents` | List agents (ACL-filtered) |
| POST | `/api/agents` | Create agent + provision K8s namespace |
| GET/PUT/DELETE | `/api/agents/{id}` | Get / update / soft-delete agent |

### Sessions & Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/agents/{id}/sessions` | Create session (private or team) |
| GET | `/api/sessions/{id}` | Session details + message history |
| WS | `/api/sessions/{id}/ws` | Real-time chat |
| POST | `/api/sessions/{id}/invite` | Invite user by email |

### ACL, Credentials, Catalog
| Method | Path | Description |
|--------|------|-------------|
| CRUD | `/api/agents/{id}/acl` | Access control management |
| CRUD | `/api/agents/{id}/credentials` | Secret management (Vault-backed) |
| GET | `/api/catalog`, `/api/catalog/search` | Browse / search agents |
| GET | `/api/inference/backends`, `/{backend}/models` | Inference backend info |

## Key Design Decisions

### Inference Router
Session Pods never call LLM backends directly. All inference goes through a centralized router in the platform namespace that determines the backend from the model name (e.g., `claude-*` → Claude API, `qwen:*` → Ollama). This keeps NetworkPolicy simple, centralizes API credentials, and preserves full claude-agent-sdk capabilities since the router speaks the Anthropic Messages API.

### Egress Proxy
All outbound HTTP/HTTPS from agent Pods is routed through a centralized egress proxy in the platform namespace via `HTTP_PROXY`/`HTTPS_PROXY` environment variables. The proxy identifies the source agent by resolving the pod's IP to its K8s namespace, then enforces per-agent egress policies stored in Redis. Supported rule types: CIDR ranges (`10.0.0.0/8`), exact domains (`api.github.com`), wildcard domains (`*.example.com`), and catch-all (`*`). Policies are deny-by-default and changes take effect immediately — updating policy writes to Redis and invalidates the proxy's cache, with no Pod restarts needed. CIDR rules are additionally enforced at the K8s NetworkPolicy level for non-HTTP traffic.

### Live Agent Config
Agent configuration (instruction, tools, policy) is passed from the database to the runtime on every message turn. Edits take effect immediately on the next message without restarting Pods or affecting other users' sessions.

### ACL Resolution
Permission resolution follows 7 steps: platform admin → agent owner → direct user ACL → team ACL → public visibility → team visibility → deny. Roles form a hierarchy: `viewer` < `user` < `admin` < `owner`.

### Agent Pod Strategy
Each agent gets a long-running Deployment with configurable spawn strategy: `lazy` (default, created on first message), `eager` (created with agent), or `manual` (admin-activated). Multiple sessions share the same Pod(s), isolated by workspace directory and bubblewrap sandbox. Idle agents (7 days) are scaled to 0, not deleted — re-activated on next message. Auto-scaling adjusts replicas based on session count per Pod.

### Session Isolation (bubblewrap)
The `claude` CLI binary in PATH is a wrapper script that runs the real binary inside a bubblewrap mount namespace. Each session sees only its own workspace directory (`/workspace/sessions/{session_id}/`); other sessions' files don't exist in the mount namespace. CLI session data is persisted to PVC at `<workspace>/.claude/` via bind-mount, enabling conversation resume across Pod restarts.

## Docker Compose Services

| Service | Port | Role |
|---------|------|------|
| `api` | 8000 | API Server |
| `web` | 3000 | Web UI |
| `postgres` | 5432 | Database |
| `redis` | 6379 | Cache, pub/sub, presence |
| `keycloak` | 8080 | OIDC provider |
| `vault` | 8200 | Secret management |
| `k3s` | 6443 | Kubernetes cluster |

## License

Private — Internal use only.
