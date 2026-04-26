# Aviary

**A self-hosted platform for building, running, and orchestrating AI agents.**

[한국어](./README.ko.md)

Aviary lets a team build their own AI agents in a web UI — give an agent an instruction, a model, and a set of tools (including [MCP](https://modelcontextprotocol.io/) servers), then chat with it or chain several agents into a workflow. Agents run inside sandboxed runtimes with per-environment network policies, so it is safe to let them touch code, data, and the internet.

The platform is designed to drop into an existing organization: it plugs into your IdP (any OIDC provider), your secrets store (HashiCorp Vault), your model providers (Anthropic, AWS Bedrock, Ollama, vLLM, …), and your Kubernetes cluster.

## Highlights

- **Web UI for the whole lifecycle** — create, configure, chat with, and delete agents; compose them into workflows; review past runs.
- **Bring your own models** — switch between hosted Anthropic, AWS Bedrock, and self-hosted Ollama or vLLM by changing a model name.
- **First-class MCP tool integration** — register MCP servers, pick which tools each agent can use, and inject per-user credentials from Vault.
- **Agent-to-Agent (A2A)** — agents can call other agents as sub-tools via `@mention`; the sub-agent's activity renders inline in the parent conversation.
- **Workflows** — chain agents and deterministic steps into DAGs on top of [Temporal](https://temporal.io/); resume, replay, and inspect runs from the UI.
- **Safe by default** — every agent turn runs inside a [bubblewrap](https://github.com/containers/bubblewrap) sandbox; outbound traffic is restricted by a Kubernetes NetworkPolicy you control per environment.
- **Multi-tenant, per-user** — OIDC login, per-user API keys and tool credentials in Vault, isolated workspaces per session.
- **Declarative infrastructure** — runtime environments are Helm releases; spin up a new one (different image, different egress) by applying a values file.

## Architecture

```
        ┌──────────────────────────────────────────────────────┐
        │                      Web UI                          │
        │     Agents · Workflows · Chat · Runs · Admin         │
        └──────────────┬─────────────────────┬─────────────────┘
                       │ REST + WebSocket    │
        ┌──────────────▼─────────┐   ┌───────▼─────────────────┐
        │      API Server        │   │      Admin Console      │
        │   Auth · CRUD · Chat   │   │  Agent / workflow defs  │
        └──────┬─────────────┬───┘   └─────────────────────────┘
               │             │
               │    ┌────────▼─────────────────────────────────┐
               │    │           Platform Services              │
               │    │   LiteLLM Gateway                        │
               │    │    ├─ LLM routing (Anthropic / Bedrock / │
               │    │    │   Ollama / vLLM …)                  │
               │    │    └─ Aggregated MCP endpoint            │
               │    │   Vault · Keycloak · Postgres · Redis    │
               │    │   Temporal · Prometheus · Grafana        │
               │    └──────────────────┬───────────────────────┘
               │                       │
        ┌──────▼───────────────────┐   │
        │    Agent Supervisor      │   │
        │   SSE proxy · abort ·    │   │
        │   metrics                │   │
        └──────────────┬───────────┘   │
                       │ HTTP          │
        ┌──────────────▼───────────────▼───────────────────────┐
        │              Agent Runtime Pool                      │
        │   Compose: in-stack `runtime` container (default)    │
        │   K8s   : per-env Helm releases                      │
        │           • default — locked-down egress, base image │
        │           • custom  — open internet + extra tooling  │
        │   Each pod is agent-agnostic; isolation is per-      │
        │   request via bubblewrap + per-session paths.        │
        └──────────────────────────────────────────────────────┘
```

## Components

| Component | What it does |
|-----------|--------------|
| **Web UI** ([web/](web/)) | Next.js frontend for end users and operators. |
| **API Server** ([api/](api/)) | OIDC-authenticated REST + WebSocket API for agents, sessions, messages, and workflows. |
| **Admin Console** ([admin/](admin/)) | Local-only operator UI for agent and workflow definitions. |
| **Agent Supervisor** ([agent-supervisor/](agent-supervisor/)) | Streams agent output from the runtime, fans events out via Redis, injects per-user credentials, handles abort. |
| **Workflow Worker** ([workflow-worker/](workflow-worker/)) | Temporal worker that drives workflow execution. |
| **Agent Runtime** ([runtime/](runtime/)) | Node.js + [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-typescript) container that actually runs the agent. Used both as the in-compose default and as the K8s pool image. |
| **LiteLLM Gateway** ([local-infra/config/litellm/](local-infra/config/litellm/)) | Single entry point for both LLM inference and MCP tool calls; routes by model name and injects per-user secrets. |
| **Helm charts** ([charts/](charts/)) | `aviary-platform` (cluster-wide: namespaces, baseline egress, shared workspace PVC) and `aviary-environment` (one release per runtime environment). |
| **Shared Python package** ([shared/](shared/)) | SQLAlchemy models, migrations, and OIDC helpers used by API + Admin + Supervisor. |

## Tech stack

| Layer | Technology |
|-------|-----------|
| Web UI | Next.js, TypeScript, Tailwind CSS, shadcn/ui |
| API + Admin + Supervisor | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Agent Runtime | Node.js, [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-typescript), Claude Code CLI |
| Workflows | [Temporal](https://temporal.io/) |
| LLM + MCP Gateway | [LiteLLM](https://github.com/BerriAI/litellm) |
| Identity | OIDC (any provider; [Keycloak](https://www.keycloak.org/) shipped for local) |
| Secrets | [HashiCorp Vault](https://www.vaultproject.io/) (with vaultless fallback for dev) |
| Data | PostgreSQL, Redis |
| Observability | OpenTelemetry, Prometheus, Grafana |
| Deployment | Helm + Kubernetes (K3s for local; EKS / your cluster for prod) |
| Sandbox | [bubblewrap](https://github.com/containers/bubblewrap), Kubernetes NetworkPolicy |

## Installation

### Prerequisites

- Docker (Docker Desktop, OrbStack, Rancher Desktop, …) with `docker compose v2`
- ~10 GB free disk for images and volumes
- Linux / macOS / WSL2

### Repo layout — two compose stacks

The repo is two compose stacks plus Helm charts. Everything is grouped into three controllable units:

| Group | What it contains | Stack |
|-------|------------------|-------|
| `service` | api, admin, web, supervisor, workflow-worker, **in-compose runtime**, postgres, redis, temporal, temporal-ui | Project root [compose.yml](compose.yml) |
| `infra` | keycloak, vault, litellm, prometheus, grafana, otel-collector, sample MCP servers (jira, confluence) | [local-infra/compose.yml](local-infra/compose.yml) |
| `runtime` | K3s + the `aviary-environment` Helm releases (`default`, `custom`) — sandboxed per-env runtime pool | [local-infra/compose.yml](local-infra/compose.yml) (`k3s` profile) + [charts/](charts/) |

The `service` stack alone is enough to chat with an agent end-to-end. `infra` and `runtime` are opt-in.

### One-shot bring-up

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh        # build + start all three groups
```

`setup-dev.sh` accepts a comma-separated subset:

```bash
./scripts/setup-dev.sh service              # services only — fastest path
./scripts/setup-dev.sh service,infra        # services + IdP/Vault/LiteLLM/observability
./scripts/setup-dev.sh runtime              # (re)build runtime images, helm apply, rollout
./scripts/setup-dev.sh                      # everything
```

The script:

1. Symlinks `local-infra/.env` to the root `.env` (single source of truth).
2. For `service` / `infra`: `docker compose build` → `docker compose up -d`.
3. For `runtime`: starts K3s, builds `aviary-runtime:latest` and `aviary-runtime-custom:latest`, imports them into K3s's containerd, renders the `aviary-platform` and two `aviary-environment` releases via `alpine/helm template | kubectl apply -f -`, and waits for rollout.

Volumes are preserved across re-runs.

### Day-to-day script reference

All scripts take the same `[group|csv]` argument; no argument means all groups.

```bash
./scripts/start-dev.sh  [groups]          # start stopped containers / scale runtime back to 1
./scripts/stop-dev.sh   [groups]          # stop containers / scale runtime to 0 (volumes kept)
./scripts/clean-dev.sh  [groups]          # remove containers AND volumes (full wipe)
./scripts/logs.sh       {infra|runtime|service}   # tail logs for one group
```

For finer-grained iteration, talk to the compose stacks directly:

```bash
docker compose up -d --build api                   # rebuild + restart one root service
docker compose restart supervisor                  # restart without rebuild
cd local-infra && docker compose restart litellm   # tweak a LiteLLM patch / config
```

Source for `api/`, `admin/`, `web/`, `agent-supervisor/`, and `workflow-worker/` is bind-mounted, so most changes hot-reload via `--reload` / `npm run dev` (see [compose.override.yml](compose.override.yml)).

## Usage by scenario

Pick the smallest group set that satisfies your scenario — there is no penalty for adding `infra` or `runtime` later.

### Scenario A — Just try it (fastest path, ~2 min)

Use the `service` group only. No IdP, no Vault, no LiteLLM, no K8s. The supervisor talks straight to the in-compose `runtime` container; LLM and MCP calls go to `llm_backends` / `mcp_servers` declared in [config.yaml](config.example.yaml).

```bash
cp config.example.yaml config.yaml          # edit: add your Anthropic API key under llm_backends
./scripts/setup-dev.sh service
```

Open the Web UI, log in as `dev-user`, create an agent, chat. See [Service endpoints](#service-endpoints) below.

### Scenario B — Full local stack (real OIDC, Vault, LiteLLM, MCP, observability)

Add the `infra` group. Now Keycloak validates JWTs, Vault stores per-user credentials, LiteLLM aggregates LLM + MCP, Grafana shows the supervisor dashboard, and the bundled `mcp-jira` / `mcp-confluence` examples are reachable.

```bash
./scripts/setup-dev.sh service,infra
```

Set the OIDC and gateway vars in `.env` (Keycloak issuer + LiteLLM URL — see [.env.example](.env.example)) and restart `api` + `supervisor`. Test users `user1@test.com` / `user2@test.com` (password `password`) are seeded in the Keycloak realm.

### Scenario C — Sandboxed per-environment runtime pool (K8s)

Add the `runtime` group when you need:

- per-environment egress policies (locked-down vs. open internet),
- per-environment custom images (extra CLIs, language toolchains),
- a realistic preview of the K8s deploy you will run in prod.

```bash
./scripts/setup-dev.sh                       # all three groups
# or, on top of an existing service+infra stack:
./scripts/setup-dev.sh runtime
```

Two runtime environments come pre-configured:

- **default** — base `aviary-runtime` image, locked-down egress (DNS + platform only). NodePort `30300`.
- **custom** — `aviary-runtime-custom` image (base + `cowsay` as a demo extra), `extraEgress: 0.0.0.0/0`. NodePort `30301`.

Per-agent routing: in the Admin Console, set `agent.runtime_endpoint` to `http://host.docker.internal:30300` (or `:30301`) to send that agent to the K8s pool instead of the in-compose runtime.

### Scenario D — Iterating on a single component

```bash
# Edit Python in api/ — already hot-reloads. Edit the Dockerfile? Rebuild:
docker compose up -d --build api

# Edit a LiteLLM patch (local-infra/config/litellm/patches/*.py):
cd local-infra && docker compose restart litellm

# Edit runtime/src/* or a Helm values file → must rebuild image + redeploy:
./scripts/setup-dev.sh runtime

# Watch logs while iterating:
./scripts/logs.sh service       # all root services
./scripts/logs.sh infra         # local-infra (litellm, keycloak, …)
./scripts/logs.sh runtime       # K8s runtime pods
```

### Scenario E — Pause / resume / wipe

```bash
./scripts/stop-dev.sh                # stop everything; volumes (DB, Vault, workspace) preserved
./scripts/start-dev.sh               # bring it back, no rebuild

./scripts/stop-dev.sh runtime        # only scale runtime pool to 0 (save laptop battery)
./scripts/start-dev.sh runtime

./scripts/clean-dev.sh service       # wipe app DB + Redis but keep Vault / Keycloak / K3s state
./scripts/clean-dev.sh               # nuke everything, full reset
```

## Service endpoints

After `setup-dev.sh` finishes, these URLs are reachable on the host. Endpoints per group:

### `service` group

| Service | URL | Purpose |
|---------|-----|---------|
| Web UI | http://localhost:3000 | End-user app |
| API Server | http://localhost:8000 | REST + WebSocket |
| Admin Console | http://localhost:8001 | Operator UI (no auth, local-only) |
| Agent Supervisor | http://localhost:9000 | Bearer-gated; streaming proxy |
| Temporal UI | http://localhost:8233 | Workflow inspector |
| Postgres | localhost:5432 | App + LiteLLM databases |
| Redis | localhost:6379 | Pub/sub, unread counters |
| Temporal | localhost:7233 | gRPC (workers connect here) |

### `infra` group

| Service | URL | Login |
|---------|-----|-------|
| Keycloak | http://localhost:8080 | `admin` / `admin` |
| Vault | http://localhost:8200 | Token: `aviary-dev-token` |
| LiteLLM Proxy | http://localhost:8090 | Master key `sk-aviary-dev` |
| LiteLLM UI | http://localhost:8090/ui | `admin` / `admin` |
| LiteLLM MCP endpoint | http://localhost:8090/mcp | Aggregated MCP |
| Grafana | http://localhost:3001 | Anonymous admin; Aviary Supervisor dashboard auto-provisioned |
| Prometheus | http://localhost:9090 | — |
| OTel Collector | localhost:4317 (gRPC) / 4318 (HTTP) | OTLP receiver |

Test accounts (in Keycloak realm `aviary`): `user1@test.com`, `user2@test.com`, password `password`.

### `runtime` group

| Endpoint | Purpose |
|----------|---------|
| http://localhost:30300 | `aviary-env-default` runtime pool (NodePort) |
| http://localhost:30301 | `aviary-env-custom` runtime pool (NodePort) |
| `kubectl` via container | `cd local-infra && docker compose --profile k3s exec k8s kubectl …` |

## Configuration

- **Single .env** — both compose stacks share [.env](.env.example) at the project root; `local-infra/.env` is auto-symlinked.
- **`config.yaml`** — declares LLM backends, MCP servers, and (in vaultless dev) per-user secrets when `VAULT_ADDR` / `VAULT_TOKEN` and `LLM_GATEWAY_URL` / `MCP_GATEWAY_URL` are unset. Start from [config.example.yaml](config.example.yaml).
- **LiteLLM** — model routing and platform-wide MCP servers in [local-infra/config/litellm/config.yaml](local-infra/config/litellm/config.yaml); per-server Vault key map in [mcp-secret-injection.yaml](local-infra/config/litellm/mcp-secret-injection.yaml).
- **Runtime environments** — each is a Helm release of `charts/aviary-environment`. Clone a `values-*.yaml`, set `image`, `extraEgress`, resource limits, and re-run `./scripts/setup-dev.sh runtime`.
- **Egress policy** — baseline `NetworkPolicy` from `charts/aviary-platform` is always applied; per-env `extraEgress` is unioned in.
- **Secrets** — per-user credentials live at `secret/aviary/credentials/{user_sub}/{namespace}/{key}` in Vault (or under the `secrets:` block in `config.yaml` for the vaultless fallback).

## Testing

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
cd agent-supervisor && uv run pytest tests/ -v
```

API/Admin tests run against a dedicated `aviary_test` Postgres database with `NullPool`, no lifespan.

## Deployment

The same Helm charts run in local K3s and in production clusters. Moving to production is primarily:

- pointing `aviary-platform` at a production-grade RWX `StorageClass` for the shared workspace PVC (e.g. EFS on AWS),
- replacing the example Keycloak realm and Vault bootstrap with your IdP and secrets store,
- supplying production model credentials and MCP server configurations,
- exposing Web, API, and LiteLLM through your ingress.

## License

See [LICENSE](./LICENSE).
