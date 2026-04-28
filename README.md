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
        └──────────────────────────┬───────────────────────────┘
                                   │ single origin
                                   │ (REST + WebSocket)
                  ┌────────────────▼────────────────┐
                  │   Edge proxy  (Caddy / ALB)     │
                  │   /api/* → API ·  /* → Web      │
                  └──────┬──────────────────┬───────┘
                         │                  │
        ┌────────────────▼───────┐  ┌───────▼─────────────────┐
        │      API Server        │  │      Admin Console      │
        │   Auth · CRUD · Chat   │  │  Agent / workflow defs  │
        └──────┬─────────────┬───┘  └─────────────────────────┘
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
| **Helm charts** ([charts/](charts/)) | `aviary-platform` (namespaces, baseline egress, shared workspace PVC, dev-only external-services proxy), `aviary-environment` (one release per runtime pool), and per-service charts for `api` / `admin` / `web` / `supervisor` / `workflow-worker`. |
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

### Repo layout — two compose stacks + Helm

Two compose stacks plus the Helm charts that ship to production:

| Stack / command | What it covers | Source |
|-----------------|----------------|--------|
| `service` group | web, api, admin, supervisor, workflow-worker, **in-compose runtime** — hot-reload dev path | Project root [compose.yml](compose.yml) |
| `infra` group | postgres, redis, temporal, temporal-ui, db-migrate, keycloak, vault, litellm, prometheus, grafana, otel-collector, sample MCP servers, K3s container | [local-infra/compose.yml](local-infra/compose.yml) |
| `local-deploy.sh` | The same charts that go to production EKS, applied to the local K3s container — chart validation path | [scripts/local-deploy.sh](scripts/local-deploy.sh) + [charts/](charts/) |

`infra` is required (postgres / redis / temporal live there); `service` adds the user-facing components on top. `local-deploy.sh` is opt-in.

### One-shot bring-up

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh        # build + start infra + service
```

`setup-dev.sh` accepts a comma-separated subset of `infra` / `service`:

```bash
./scripts/setup-dev.sh infra                # platform deps only (postgres, redis, temporal, keycloak, …)
./scripts/setup-dev.sh infra,service        # platform deps + user-facing services
./scripts/setup-dev.sh                      # both
```

The script symlinks `local-infra/.env` to the root `.env`, then runs `docker compose build` → `docker compose up -d` for each requested group. Volumes are preserved across re-runs.

To validate the production Helm charts on the local K3s container:

```bash
./scripts/local-deploy.sh setup                      # build all images, ctr import, helm apply
./scripts/local-deploy.sh setup --only=aviary-api    # rebuild + redeploy a subset
./scripts/local-deploy.sh logs aviary-api            # tail one chart's logs
./scripts/local-deploy.sh stop                       # scale all platform deploys to 0
./scripts/local-deploy.sh clean                      # helm-delete every release
```

`local-deploy.sh setup` brings up the K3s container, builds the api / supervisor / workflow-worker / runtime / web / db-migrate images, imports them into containerd, then applies the charts in dependency order: `aviary-platform` → `aviary-api` (with a pre-install `db-migrate` Job) → `aviary-supervisor` → `aviary-workflow-worker` → `aviary-env-{default,custom}` → `aviary-web`. Image digests are cached so re-runs only rebuild what changed.

### Day-to-day script reference

```bash
./scripts/start-dev.sh  [groups]          # start stopped compose containers
./scripts/stop-dev.sh   [groups]          # stop compose containers (volumes kept)
./scripts/clean-dev.sh  [groups]          # remove compose containers AND volumes (full wipe)
./scripts/logs.sh       {infra|service}   # tail logs for one compose group

./scripts/local-deploy.sh {setup|start|stop|clean|logs}   # K8s side
```

For finer-grained iteration, talk to the compose stacks directly:

```bash
docker compose up -d --build api                   # rebuild + restart one root service
docker compose restart supervisor                  # restart without rebuild
cd local-infra && docker compose restart litellm   # tweak a LiteLLM patch / config
```

Source for `api/`, `admin/`, `web/`, `agent-supervisor/`, and `workflow-worker/` is bind-mounted, so most changes hot-reload via `--reload` / `npm run dev` (see [compose.override.yml](compose.override.yml)).

## Usage by scenario

`infra` is required for any scenario (it owns postgres / redis / temporal). Add `service` for the daily hot-reload dev path; reach for `local-deploy.sh` for chart validation.

### Scenario A — Minimal local dev stack

Bring up infra + service compose. Supervisor talks straight to the in-compose `runtime`; LLM/MCP calls route through whatever is configured in [config.yaml](config.example.yaml).

```bash
cp config.example.yaml config.yaml          # edit: add your Anthropic API key under llm_backends
./scripts/setup-dev.sh                      # infra + service
```

Open the Web UI, log in as `dev-user`, create an agent, chat. See [Service endpoints](#service-endpoints) below.

### Scenario B — Wire up real IdP / Vault / LiteLLM

`infra` already ships Keycloak, Vault, LiteLLM, MCP, and observability. Set the OIDC and gateway vars in `.env` (see [.env.example](.env.example)) and restart `api` + `supervisor` (`docker compose restart api supervisor`). Test users `user1@test.com` / `user2@test.com` (password `password`) are seeded in the Keycloak realm.

### Scenario C — Validate the production Helm charts on local K3s

Use `local-deploy.sh` when you need:

- per-environment egress policies (locked-down vs. open internet) on the runtime pool,
- per-environment custom images (extra CLIs, language toolchains),
- a realistic preview of the EKS deploy — web / api / supervisor / workflow-worker / runtime running on the same K3s as a prod GitOps target would.

```bash
./scripts/setup-dev.sh infra              # postgres / redis / temporal / keycloak / litellm / vault
./scripts/local-deploy.sh setup           # web / api / supervisor / workflow-worker / runtime → K3s
```

Two runtime environments come pre-configured:

- **default** — base `aviary-runtime` image, locked-down egress (DNS + platform only). NodePort `30300`.
- **custom** — `aviary-runtime-custom` image (base + `cowsay` as a demo extra), `extraEgress: 0.0.0.0/0`. NodePort `30301`.

Per-agent routing: in the Admin Console, set `agent.runtime_endpoint` to `http://host.docker.internal:30300` (or `:30301`) to send that agent to the K8s pool instead of the in-compose runtime.

The off-cluster Caddy proxy (`local-infra/compose.yml` `proxy-k3s`, host port `:80`) and the service-compose Caddy proxy (host port `:3000`) use different ports so they can coexist while sharing infra. If you keep service compose running alongside, stop its app components first (`docker compose stop web api supervisor workflow-worker`) so the two stacks don't race on the same database.

### Scenario D — Iterating on a single component

```bash
# Edit Python in api/ — already hot-reloads. Edit the Dockerfile? Rebuild:
docker compose up -d --build api

# Edit a LiteLLM patch (local-infra/config/litellm/patches/*.py):
cd local-infra && docker compose restart litellm

# Edit runtime/src/* or a Helm values file → rebuild + redeploy that one chart:
./scripts/local-deploy.sh setup --only=aviary-env-default
./scripts/local-deploy.sh setup --only=aviary-api    # or any other chart

# Watch logs while iterating:
./scripts/logs.sh service                            # all root services
./scripts/logs.sh infra                              # local-infra (litellm, keycloak, …)
./scripts/local-deploy.sh logs aviary-env-default    # K8s runtime pods
./scripts/local-deploy.sh logs aviary-api            # any other K8s deploy
```

### Scenario E — Pause / resume / wipe

```bash
./scripts/stop-dev.sh                # stop both compose groups; volumes preserved
./scripts/start-dev.sh               # bring them back, no rebuild

./scripts/local-deploy.sh stop       # scale K8s deploys (incl. runtime pool) to 0
./scripts/local-deploy.sh start      # scale them back to 1

./scripts/clean-dev.sh service       # wipe app DB + Redis but keep Vault / Keycloak / K3s state
./scripts/clean-dev.sh               # nuke both compose groups (including K3s data volume)
./scripts/local-deploy.sh clean      # helm-delete every chart release (K3s container kept)
```

## Service endpoints

After `setup-dev.sh` finishes, these URLs are reachable on the host. Endpoints per group:

### `service` group

| Service | URL | Purpose |
|---------|-----|---------|
| Browser entry (Caddy proxy) | http://localhost:3000 | `/api/*` → API · `/` → Web — mirrors the prod ALB |
| Admin Console | http://localhost:8001 | Operator UI (no auth, local-only) |

The API and Supervisor live on internal compose DNS only — `api:8000` / `supervisor:9000`. They are not published to the host; reach them via `docker compose exec` or hit them through the Caddy proxy.

### `infra` group

| Service | URL | Login / purpose |
|---------|-----|-----------------|
| Postgres | localhost:5432 | App + LiteLLM + Keycloak + Temporal databases |
| Redis | localhost:6379 | Pub/sub, unread counters |
| Temporal | localhost:7233 | gRPC (workers connect here) |
| Temporal UI | http://localhost:8233 | Workflow inspector |
| Keycloak | http://localhost:8080 | `admin` / `admin` |
| Vault | http://localhost:8200 | Token: `dev-root-token` |
| LiteLLM Proxy | http://localhost:8090 | Master key `sk-aviary-dev` |
| LiteLLM UI | http://localhost:8090/ui | `admin` / `admin` |
| LiteLLM MCP endpoint | http://localhost:8090/mcp | Aggregated MCP |
| Grafana | http://localhost:3001 | Anonymous admin; Aviary Supervisor dashboard auto-provisioned |
| Prometheus | http://localhost:9090 | — |
| OTel Collector | localhost:4317 (gRPC) / 4318 (HTTP) | OTLP receiver |

Test accounts (in Keycloak realm `aviary`): `user1@test.com`, `user2@test.com`, password `password`.

### `local-deploy.sh` (K3s)

After `./scripts/local-deploy.sh setup` finishes, the off-cluster Caddy proxy (`local-infra/compose.yml` `proxy-k3s`) sits in front of the K3s NodePorts — same role as the prod ALB.

| Endpoint | Chart / purpose |
|----------|-----------------|
| http://localhost | Caddy proxy → `aviary-web` + `/api/*` → `aviary-api` (single browser entry) |
| http://localhost:30300 | `aviary-env-default` runtime pool |
| http://localhost:30301 | `aviary-env-custom` runtime pool |
| `kubectl` via container | `cd local-infra && docker compose --profile k3s exec k8s kubectl …` |

`aviary-admin` and `aviary-supervisor` are ClusterIP only — reach them with `kubectl port-forward -n platform svc/aviary-admin 8001:8001` (or `svc/aviary-supervisor 9000:9000`). The web/api NodePorts (31301/31000) are the proxy's upstream — not browser-facing. Postgres / Redis / Temporal / Keycloak / Vault / LiteLLM stay in compose and are exposed to the cluster via the `aviary-platform` external-services proxy.

## Configuration

- **Single .env** — both compose stacks share [.env](.env.example) at the project root; `local-infra/.env` is auto-symlinked.
- **`config.yaml`** — declares LLM backends, MCP servers, and (in vaultless dev) per-user secrets when `VAULT_ADDR` / `VAULT_TOKEN` and `LLM_GATEWAY_URL` / `MCP_GATEWAY_URL` are unset. Start from [config.example.yaml](config.example.yaml).
- **LiteLLM** — model routing and platform-wide MCP servers in [local-infra/config/litellm/config.yaml](local-infra/config/litellm/config.yaml); per-server Vault key map in [mcp-secret-injection.yaml](local-infra/config/litellm/mcp-secret-injection.yaml).
- **Runtime environments** — each is a Helm release of `charts/aviary-environment`. Clone a `values-*.yaml`, set `image`, `extraEgress`, resource limits, then `./scripts/local-deploy.sh setup --only=aviary-env-<name>` to apply.
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
