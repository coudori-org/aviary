# Aviary

**Multi-Tenant AI Agent Platform**

[한국어](./README.ko.md)

Aviary is an enterprise platform where users can create, configure, deploy, and use purpose-built AI agents through a web UI. Each agent runs in an isolated Kubernetes namespace, and each user session gets a dedicated Pod for kernel-level isolation.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                       Web UI (Next.js 15)                      │
│   Agent Catalog · Create/Edit · Chat Sessions · ACL Settings   │
└──────────────┬────────────────────────────────────────────────┘
               │ REST + WebSocket
┌──────────────▼────────────────────────────────────────────────┐
│                    API Server (FastAPI)                         │
│   OIDC Auth · Agent CRUD · Session Mgr · ACL · Vault Client   │
└──────────────┬────────────────────────────────────────────────┘
               │ K8s API Proxy
┌──────────────▼────────────────────────────────────────────────┐
│                    Kubernetes Cluster                           │
│                                                                │
│  NS: platform                                                  │
│  ┌──────────────────┐ ┌────────────────┐ ┌──────────────────┐ │
│  │ Inference Router  │ │ Credential     │ │ Image Warmer     │ │
│  │ (LLM gateway)    │ │ Proxy (Vault)  │ │ (DaemonSet)      │ │
│  └────────┬─────────┘ └────────────────┘ └──────────────────┘ │
│           │                                                    │
│     ┌─────┴──────────────────────┐                             │
│     ▼              ▼             ▼                             │
│  Claude API    Ollama/vLLM    Bedrock                          │
│                                                                │
│  NS: agent-{id}           NS: agent-{id}                      │
│  ┌─────────────────┐     ┌─────────────────┐                  │
│  │ Session Pod      │     │ Session Pod      │                  │
│  │ claude-agent-sdk │     │ claude-agent-sdk │                  │
│  │ + Claude Code CLI│     │ + Claude Code CLI│                  │
│  │ PVC: /workspace  │     │ PVC: /workspace  │                  │
│  └─────────────────┘     └─────────────────┘                  │
└───────────────────────────────────────────────────────────────┘
```

## Key Features

- **Per-Session Pod Isolation** — Each chat session runs in its own K8s Pod with a persistent workspace (PVC)
- **Namespace-per-Agent** — NetworkPolicy, ResourceQuota, and ServiceAccount scoped per agent
- **claude-agent-sdk Powered** — Full [Claude Code](https://docs.anthropic.com/en/docs/claude-code) harness including tools, sub-agents, MCP servers, file I/O, and shell execution
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
├── runtime/                 # Agent Runtime (runs in session Pods)
│   └── app/                 # claude-agent-sdk harness, history
├── inference-router/        # LLM Gateway (platform namespace)
│   └── app/                 # Anthropic API proxy, backend routing
├── credential-proxy/        # Secret injection proxy (platform namespace)
│   └── app/                 # Vault client, session resolver
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

# Rebuild runtime image (runs inside K3s)
docker build -t aviary-runtime:latest ./runtime/
docker save aviary-runtime:latest | docker compose exec -T k3s ctr images import -
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

### Live Agent Config
Agent configuration (instruction, tools, policy) is passed from the database to the runtime on every message turn. Edits take effect immediately on the next message without restarting Pods or affecting other users' sessions.

### ACL Resolution
Permission resolution follows 7 steps: platform admin → agent owner → direct user ACL → team ACL → public visibility → team visibility → deny. Roles form a hierarchy: `viewer` < `user` < `admin` < `owner`.

### Session Pod Lifecycle
Pods are created on first message and reuse existing PVCs for workspace persistence. On restart, stale Pod references are detected and cleaned up automatically — the application self-heals without external intervention.

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
