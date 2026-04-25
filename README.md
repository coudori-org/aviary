# Aviary

**A self-hosted platform for building, running, and orchestrating AI agents.**

[한국어](./README.ko.md)

Aviary is an open-source, multi-tenant platform for teams that want to build and operate their own AI agents. Create an agent in the web UI, give it an instruction and a set of tools (including [MCP](https://modelcontextprotocol.io/) servers), pick a model, and chat with it — or compose several agents into a workflow. Agents run inside sandboxed, network-policed runtimes so you can safely let them touch code, data, and the internet.

The platform is designed to be dropped into an existing organization: it plugs into your identity provider (OIDC), your secrets store (Vault), your model providers (Anthropic / AWS Bedrock / self-hosted Ollama or vLLM), and your Kubernetes cluster.

## Highlights

- **Web UI for the whole lifecycle** — browse, create, configure, chat with, and delete agents; compose them into workflows; monitor past runs.
- **Bring your own models** — swap between hosted Anthropic, AWS Bedrock, and self-hosted Ollama or vLLM by changing a model name.
- **First-class MCP tool integration** — plug in MCP servers, let users pick which tools each agent can use, and inject per-user credentials from Vault so tool calls are authenticated without leaking secrets.
- **Agent-to-Agent (A2A)** — agents can call other agents as sub-tools via `@mention`; sub-agent activity renders inline in the parent conversation.
- **Workflows** — chain agents and deterministic steps into DAGs backed by a durable workflow engine; resume, replay, and inspect runs from the UI.
- **Safe by default** — every agent turn runs inside a [bubblewrap](https://github.com/containers/bubblewrap) sandbox with its own mount, PID, and network view; outbound traffic is restricted by a Kubernetes NetworkPolicy you control per environment.
- **Multi-tenant and per-user** — OIDC login, per-user API keys and tool credentials stored in Vault, isolated workspaces per session.
- **Declarative infrastructure** — runtime environments are Helm releases; spin up a new environment (different image, different egress policy, different model pool) by applying a values file.
- **Production-ready ops** — Prometheus metrics, a pre-provisioned Grafana dashboard, structured logs, and a supervisor that cleanly aborts in-flight streams on user cancel.
- **Single-command local bring-up** — one script builds the images, applies the Helm charts, and starts every service on your laptop.

## Architecture

```
        ┌──────────────────────────────────────────────────────┐
        │                      Web UI                          │
        │    Agents · Workflows · Chat · Runs · Admin          │
        └──────────────┬─────────────────────┬─────────────────┘
                       │ REST + WebSocket    │
        ┌──────────────▼─────────┐   ┌───────▼─────────────────┐
        │      API Server        │   │      Admin Console      │
        │   Auth · CRUD · Chat   │   │  Agent / tool / secret  │
        │   Workflow control     │   │       management        │
        └──────┬─────────────┬───┘   └─────────────┬───────────┘
               │             │                     │
               │    ┌────────▼─────────────────────▼──────────┐
               │    │           Platform Services              │
               │    │                                          │
               │    │   LiteLLM Gateway                        │
               │    │    ├─ LLM routing (Anthropic, Bedrock,   │
               │    │    │   Ollama, vLLM, …)                  │
               │    │    └─ Aggregated MCP endpoint            │
               │    │                                          │
               │    │   Vault · Keycloak · Postgres · Redis    │
               │    │   Prometheus · Grafana                   │
               │    └──────────────────┬───────────────────────┘
               │                       │
        ┌──────▼───────────────────┐   │
        │    Agent Supervisor      │   │
        │  Streams agent output,   │   │
        │  handles abort, emits    │   │
        │  metrics                 │   │
        └──────────────┬───────────┘   │
                       │ HTTP          │
        ┌──────────────▼───────────────▼───────────────────────┐
        │                 Kubernetes Cluster                   │
        │                                                      │
        │   Runtime environments (Helm releases):              │
        │     • default  — locked-down egress, base image      │
        │     • custom   — open internet + extra tooling       │
        │     • …add your own                                  │
        │                                                      │
        │   Each environment = Deployment + Service,           │
        │   sharing one cluster-wide workspace volume.         │
        │   Every pod is agent-agnostic; isolation happens     │
        │   per-request via bubblewrap + per-session paths.    │
        └──────────────────────────────────────────────────────┘
```

### Component responsibilities

- **Web UI** — Next.js application for end users and operators.
- **API Server** — OIDC-authenticated REST + WebSocket API for agents, sessions, messages, and workflows.
- **Admin Console** — operator UI for agent definitions, MCP server registration, and per-user credential management.
- **Agent Supervisor** — streams agent output from the runtime pools, fans events out to connected clients, and cancels in-flight runs on user abort.
- **LiteLLM Gateway** — single entry point for both LLM inference and MCP tool calls; routes by model name and injects per-user credentials.
- **Agent Runtime** — the pool of pods that actually execute agents. Every pod serves every agent; per-request sandboxing is kernel-level.
- **Shared workspace volume** — a single cluster-wide volume where each session's files live. Agents in the same session can exchange files; sessions are isolated from each other.
- **Platform services** — Postgres (application state), Redis (pub/sub + caches), Keycloak (identity), Vault (secrets), Prometheus + Grafana (observability).

## Tech stack

| Layer | Technology |
|-------|-----------|
| Web UI | Next.js, TypeScript, Tailwind CSS, shadcn/ui |
| API + Admin | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Agent Runtime | Node.js, [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-typescript), Claude Code CLI |
| Agent Supervisor | Python, FastAPI, Redis, Prometheus client |
| Workflows | [Temporal](https://temporal.io/) |
| LLM + MCP Gateway | [LiteLLM](https://github.com/BerriAI/litellm) |
| Identity | [Keycloak](https://www.keycloak.org/) (OIDC) |
| Secrets | [HashiCorp Vault](https://www.vaultproject.io/) |
| Data | PostgreSQL, Redis |
| Observability | Prometheus, Grafana |
| Deployment | Helm, Kubernetes (K3s for local dev, EKS for production) |
| Sandbox | [bubblewrap](https://github.com/containers/bubblewrap), Kubernetes NetworkPolicy |

## Getting started

**Prerequisites:** Docker Desktop (or any compatible container runtime).

```bash
git clone <repository-url>
cd aviary
./scripts/dev-up.sh
```

`dev-up.sh` brings up the local-infra stack (`local-infra/compose.yml` — postgres, redis, keycloak, vault, temporal, litellm, observability, MCP backends) and then the project-root services (`compose.yml` — api, admin, web, agent-supervisor, workflow-worker), runs database migrations, and waits for everything to report ready.

K3s + the Helm charts that define the runtime environments are no longer started by default — that flow is opt-in via `./scripts/chart-test.sh`.

Once the script finishes:

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API Server | http://localhost:8000 |
| Admin Console | http://localhost:8001 |
| LiteLLM Proxy / UI | http://localhost:8090 · http://localhost:8090/ui |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| Keycloak | http://localhost:8080 |

Test accounts: `user1@test.com` and `user2@test.com` (password: `password`).

Day-to-day commands:

```bash
./scripts/dev-up.sh                          # Bring up everything (infra → services)
./scripts/dev-down.sh                        # Stop (volumes preserved)
./scripts/dev-down.sh --volumes              # Reset everything, including data

cd infra    && docker compose up -d          # Just the infra stack
cd services && docker compose up -d --build  # Just the services stack (assumes infra is up)
cd services && docker compose restart api    # Single-service restart
```

Source code is bind-mounted into the application containers, so changes to `api/`, `admin/`, `web/`, and `agent-supervisor/` hot-reload.

## Usage

1. **Log in** to the Web UI with a test account.
2. **Create an agent** — give it a name, an instruction, and pick a model. Optionally attach MCP tools and other agents (for A2A).
3. **Chat** with the agent. Agent output streams in real time; click *Stop* any time to abort.
4. **Compose workflows** — chain multiple agent calls and deterministic steps into a DAG; trigger them from the UI or the API.
5. **Monitor** activity in Grafana; operators manage agents, MCP servers, and per-user credentials from the Admin Console.

## Project structure

```
aviary/
├── api/                  # API Server (user-facing)
├── admin/                # Admin Console (operator-facing)
├── web/                  # Next.js Web UI
├── agent-supervisor/     # SSE proxy + Prometheus metrics
├── workflow-worker/      # Temporal worker
├── runtime/              # Agent Runtime image (deployed to K3s)
├── shared/               # Shared Python package (models, migrations, OIDC)
├── compose.yml           # Wires the services above for local dev
├── compose.override.yml  # bind-mounts + dev commands
├── pyproject.toml        # uv workspace root
├── uv.lock
├── local-infra/          # Pre-provisioned in prod; reproduced locally
│   ├── compose.yml             # postgres, redis, keycloak, vault, temporal,
│   │                           # litellm, prometheus, grafana, mcp-*, k3s (profile)
│   ├── config/                 # litellm patches, keycloak realm, vault, k3s, observability
│   ├── mcp-servers/            # Example MCP server implementations (jira, confluence)
│   └── scripts/                # init-db.sql, vault-init.sh
├── charts/               # Helm charts (we own these — gitops-deployed in prod)
│   ├── aviary-platform/        # Cluster-wide resources (namespaces, egress, shared workspace)
│   └── aviary-environment/     # One runtime environment per release
└── scripts/              # dev-up / dev-down / chart-test / quick-rebuild / smoke-test
```

## Configuration

Compose-level knobs live in `local-infra/compose.yml` / project-root `compose.yml`; runtime overrides go in each stack's `.env`. Helm `values-*.yaml` files under `charts/` cover K8s deploy. Notable knobs:

- **Model routing** — `local-infra/config/litellm/config.yaml` defines which LLM backends LiteLLM forwards to based on model name.
- **MCP servers** — declare platform-wide MCP servers in `local-infra/config/litellm/config.yaml`; operators can register additional servers at runtime through LiteLLM's UI.
- **Runtime environments** — each environment is a Helm release of `charts/aviary-environment` with its own image, egress rules, and resource limits. Add or clone a values file and apply it via `./scripts/helm-apply.sh`.
- **Egress policy** — a baseline `NetworkPolicy` from `charts/aviary-platform` always applies; extra rules per environment are unioned in.
- **Secrets** — per-user credentials (model API keys, tool tokens) are stored in Vault under a per-user path and injected by the gateway, never by the runtime pods.

## Testing

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
cd agent-supervisor && uv run pytest tests/ -v
```

## Deployment

The same Helm charts run in local K3s and in production clusters. Moving to production is primarily a matter of:

- pointing the charts at a production-grade `StorageClass` for the shared workspace volume (for example EFS on AWS),
- replacing the example Keycloak realm and Vault bootstrap with your organization's IdP and secrets store,
- supplying production-appropriate model credentials and MCP server configurations,
- and exposing the Web UI, API, and LiteLLM through your ingress of choice.

## License

See [LICENSE](./LICENSE).
