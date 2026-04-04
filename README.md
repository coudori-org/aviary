# Aviary

**Multi-Tenant AI Agent Platform**

[한국어](./README.ko.md)

Aviary is an enterprise platform where users can create, configure, and use purpose-built AI agents through a web UI. Each agent runs in an isolated Kubernetes namespace with long-running Pods that serve multiple sessions concurrently, isolated at the kernel level via bubblewrap sandboxing.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Web UI (Next.js 15)                     │
│    Agent Catalog · Create/Edit · Chat Sessions · ACL Settings  │
└───────────────┬────────────────────────────────────────────────┘
                │ REST + WebSocket
┌───────────────▼────────────────────────────────────────────────┐
│                     API Server (FastAPI)                        │
│      OIDC Auth · Agent CRUD · Session Mgr · ACL · Chat         │
└───┬───────────┬───────────┬────────────────────────────────────┘
    │           │           │
    │           │           │           ┌────────────────────────┐
    │           │           │           │  Admin Console (:8001) │
    │           │           │           │  Policy · Scaling ·    │
    │           │           │           │  Deployments · Web UI  │
    │           │           │           └───────────┬────────────┘
    │           │           │                       │
    │           │           │
    │           │   ┌───────▼────────────────────────────────────┐
    │           │   │           Platform Services                │
    │           │   │                                            │
    │           │   │  ┌─────────────────┐  ┌──────────────────┐ │
    │           │   │  │ LiteLLM Gateway │  │ Secret Provider │ │
    │           │   │  │  (LLM proxy)    │  │  (Vault secrets) │ │
    │           │   │  └────────┬────────┘  └──────────────────┘ │
    │           │   │           │                                 │
    │           │   │     ┌─────┴───────────────────┐            │
    │           │   │     ▼            ▼            ▼            │
    │           │   │  Claude API   Ollama/vLLM   Bedrock        │
    │           │   └────────────────────────────────────────────┘
    │           │
    │           │ HTTP (:9000)
    │   ┌───────▼────────────────────────────────────────────────┐
    │   │                   Kubernetes Cluster                    │
    │   │                                                        │
    │   │  ┌─── NS: platform ──────────────────────────────────┐ │
    │   │  │  ┌─────────────────┐  ┌────────────────────────┐  │ │
    │   │  │  │  Egress Proxy   │  │   Agent Supervisor     │  │ │
    │   │  │  │  (forward proxy │  │   (K8s gateway,         │  │ │
    │   │  │  │   + allowlist)  │  │    NodePort 30900)      │  │ │
    │   │  │  └────────┬────────┘  └────────────────────────┘  │ │
    │   │  │           │                                        │ │
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
    │   │  │  LLM ──▶ LiteLLM Gateway│  │                     │ │
    │   │  │  Secrets ▶ Secret Prov.   │  │  NetworkPolicy:     │ │
    │   │  │  HTTP ──▶ Egress Proxy   │  │    deny-by-default  │ │
    │   │  └──────────────────────────┘  └─────────────────────┘ │
    │   └────────────────────────────────────────────────────────┘
    │
    │  ┌───────────────┐  ┌──────────────┐  ┌────────────────┐
    └─▶│  PostgreSQL    │  │    Redis      │  │   Keycloak     │
       │  DB, sessions  │  │  pub/sub,     │  │   OIDC auth    │
       │  ACL, agents   │  │  presence │  │   team sync    │
       └───────────────┘  └──────────────┘  └────────────────┘
```

**API Server** handles user-facing operations (auth, chat, agent config). **Admin Console** edits infrastructure configuration (policies, deployments). **Agent Supervisor** manages runtime resources, auto-scaling, and idle cleanup inside K8s. **Egress Proxy** enforces per-agent outbound traffic rules.

## Key Features

- **Agent-per-Pod with Multi-Session** — Each agent gets a long-running Deployment (1-N replicas) serving multiple sessions concurrently, auto-scaled based on session load
- **Bubblewrap Session Isolation** — Each session runs inside a bwrap mount namespace; other sessions' files are invisible at the kernel level
- **Namespace-per-Agent** — NetworkPolicy, ResourceQuota, and ServiceAccount scoped per agent
- **Egress Proxy** — All outbound HTTP/HTTPS from agent Pods routed through a centralized proxy with per-agent allowlists (CIDR, exact domain, wildcard `*.example.com`); deny-by-default, policy changes take effect immediately without Pod restarts
- **claude-agent-sdk Powered** — Full [Claude Code](https://docs.anthropic.com/en/docs/claude-code) harness via `ClaudeSDKClient` including tools, sub-agents, MCP servers, file I/O, and shell execution
- **LiteLLM Gateway** — All LLM calls routed through [LiteLLM](https://github.com/BerriAI/litellm) OSS proxy; backend determined by model name prefix (`anthropic/`, `ollama/`, `vllm/`, `bedrock/`), natively compatible with Anthropic SDK
- **Multi-Backend Inference** — Claude API, Ollama, vLLM, AWS Bedrock; add new backends via config, no code or NetworkPolicy changes required
- **Live Config Updates** — Agent config (instruction, tools) is passed from DB on every message; edits take effect immediately without Pod restarts
- **OIDC Auth + Team Sync** — Keycloak (dev) / Okta (prod); IdP groups auto-sync to Aviary teams on login
- **API / Admin Separation** — Separate services for user operations (API) and infrastructure management (Admin Console)
- **Granular ACL** — Permission resolution with role hierarchy (`viewer` < `user` < `admin` < `owner`)
- **Secret Provider** — Secrets never enter session Pods; injected from Vault via a shared proxy
- **Real-time Chat** — WebSocket streaming with Redis pub/sub for multi-user shared sessions

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Web UI | Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| API Server | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Agent Runtime | TypeScript, Node.js 22, claude-agent-sdk, Claude Code CLI |
| LLM Gateway | [LiteLLM](https://github.com/BerriAI/litellm) — unified LLM proxy (Anthropic, OpenAI, Bedrock, Ollama, vLLM) |
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
├── api/                     # API Server (FastAPI) — user-facing
│   ├── app/
│   │   ├── auth/            # OIDC validation, team sync
│   │   ├── db/              # Re-exports shared DB models
│   │   ├── routers/         # REST + WebSocket endpoints
│   │   ├── services/        # Business logic (agent, session, vault, acl, redis)
│   │   └── schemas/         # Pydantic models
│   └── tests/
├── admin/                   # Admin Console (FastAPI) — operator-facing
│   ├── app/
│   │   ├── routers/         # Agent, deployment, policy management
│   │   ├── services/        # Controller client, redis, scaling
│   │   ├── templates/       # Jinja2 web UI
│   │   └── static/          # CSS
│   └── tests/
├── shared/                  # Shared DB package (used by api + admin)
│   └── aviary_shared/
│       └── db/              # SQLAlchemy models, session factory, migrations
├── web/                     # Web UI (Next.js 15)
│   └── src/
│       ├── app/             # Pages (agents, sessions, login)
│       ├── components/      # Chat, agent management, UI primitives
│       └── lib/             # API client, auth, WebSocket
├── agent-supervisor/         # Agent Supervisor (FastAPI, runs in K8s)
│   └── app/                 # K8s gateway, agent-centric + K8s-specific APIs
├── runtime/                 # Agent Runtime (runs in agent Pods)
│   └── src/                 # claude-agent-sdk harness, session manager
├── config/litellm/          # LiteLLM Gateway config
├── secret-provider/        # Secret injection proxy
├── egress-proxy/            # HTTP/HTTPS egress proxy
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

This single command builds all images, starts all services, runs DB migrations, and provisions the K8s cluster.

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API Server | http://localhost:8000 |
| Admin Console | http://localhost:8001 |
| LiteLLM Gateway | http://localhost:8090 |
| Keycloak Admin | http://localhost:8080 (admin/admin) |
| Vault | http://localhost:8200 |

### Test Accounts

| Email | Password | Teams |
|-------|----------|-------|
| user1@test.com | password | engineering, product |
| user2@test.com | password | data-science |

### Everyday Commands

```bash
docker compose up -d          # Start
docker compose down           # Stop (data preserved)
docker compose down -v        # Stop + delete all data
docker compose logs -f api    # Tail logs
```

### Development

Source code is bind-mounted into containers. Edits to `api/` and `web/` are reflected automatically via hot reload. LiteLLM config changes require `docker compose restart litellm`.

```bash
# Rebuild after dependency changes
docker compose up -d --build api
docker compose up -d --build web

# Rebuild K8s images (runtime, egress-proxy, agent-supervisor)
docker build -t aviary-runtime:latest ./runtime/
docker build -t aviary-egress-proxy:latest ./egress-proxy/
docker build -t aviary-agent-supervisor:latest -f agent-supervisor/Dockerfile .
docker save aviary-runtime:latest aviary-egress-proxy:latest aviary-agent-supervisor:latest | docker compose exec -T k8s ctr images import -
```

## Testing

```bash
# API server tests
docker compose exec api pytest tests/ -v

# Admin console tests
docker compose exec admin pytest tests/ -v
```

API and admin tests covering health, agent CRUD, ACL (visibility, grants, permission deny), sessions (create, list, access control, archive), policies, and deployments. Uses a dedicated `aviary_test` database and token-based mock auth for multi-user scenarios.

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
| POST | `/api/agents` | Create agent (config only) |
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

### LiteLLM Gateway
Session Pods never call LLM backends directly. All inference goes through a [LiteLLM](https://github.com/BerriAI/litellm) OSS proxy that routes requests based on the model name prefix (e.g., `anthropic/claude-sonnet-4-6` → Claude API, `ollama/gemma4:26b` → Ollama, `vllm/...` → vLLM). LiteLLM natively supports the Anthropic Messages API (`/v1/messages`), so claude-agent-sdk works transparently without protocol translation. This centralizes API credentials, rate limiting, and observability. New backends are added via config file (`config/litellm/config.yaml`) without code changes.

### Egress Proxy
All outbound HTTP/HTTPS from agent Pods is routed through a centralized forward proxy via `HTTP_PROXY`/`HTTPS_PROXY` environment variables. The proxy identifies the source agent by resolving the pod's IP to its K8s namespace, then enforces per-agent egress policies. Supported rule types: CIDR ranges, exact domains, wildcard domains (`*.example.com`), and catch-all. Policies are deny-by-default and changes take effect immediately without Pod restarts.

### Live Agent Config
Agent configuration (instruction, tools, policy) is passed from the database to the runtime on every message turn. Edits take effect immediately on the next message without restarting Pods or affecting other users' sessions.

### ACL Resolution
Permission resolution follows 6 steps: agent owner → direct user ACL → team ACL → public visibility → team visibility → deny. Roles form a hierarchy: `viewer` < `user` < `admin` < `owner`.

### Agent Pod Strategy
Each agent gets a long-running Deployment with configurable spawn strategy: `lazy` (default, created on first message) or `eager` (created with agent). Multiple sessions share the same Pod(s), isolated by workspace directory and bubblewrap sandbox. Idle agents (7 days) are scaled to 0, not deleted — re-activated on next message.

### Session Isolation (bubblewrap)
The `claude` CLI binary in PATH is a wrapper script that runs the real binary inside a bubblewrap mount namespace. Each session sees only its own workspace directory (`/workspace/sessions/{session_id}/`); other sessions' files don't exist in the mount namespace. CLI session data is persisted to PVC, enabling conversation resume across Pod restarts.

## Services

| Service | Port | Role |
|---------|------|------|
| `api` | 8000 | API Server (user-facing) |
| `admin` | 8001 | Admin Console (operator-facing, no auth) |
| `web` | 3000 | Web UI |
| `litellm` | 8090 | LLM gateway (LiteLLM) |
| `secret-provider` | K8s internal | Secret injection (Vault)|
| `postgres` | 5432 | Database |
| `redis` | 6379 | Cache, pub/sub, presence |
| `keycloak` | 8080 | OIDC provider |
| `vault` | 8200 | Secret management |
| `k8s` | 6443 | Kubernetes cluster |

## License

Private — Internal use only.
