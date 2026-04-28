# Aviary

**AI 에이전트를 만들고 운영하고 오케스트레이션하는 셀프 호스팅 플랫폼.**

[English](./README.md)

Aviary는 팀이 자체 AI 에이전트를 직접 만들고 운영할 수 있게 해주는 오픈소스 멀티테넌트 플랫폼입니다. 웹 UI에서 에이전트에게 instruction과 모델, 도구([MCP](https://modelcontextprotocol.io/) 서버 포함)를 지정한 뒤 바로 대화하거나, 여러 에이전트를 워크플로우로 엮어 실행할 수 있습니다. 모든 에이전트는 샌드박스 런타임과 환경별 네트워크 정책 안에서 동작하기 때문에, 코드·데이터·인터넷을 다루게 해도 안전합니다.

Aviary는 기존 조직 환경에 그대로 얹혀 쓰도록 설계되었습니다 — 사내 OIDC IdP, HashiCorp Vault, 모델 공급자(Anthropic / AWS Bedrock / 자체 호스팅 Ollama·vLLM), Kubernetes 클러스터와 직접 연동됩니다.

## 핵심 기능

- **전체 라이프사이클을 한 웹 UI에서** — 에이전트 생성·설정·대화·삭제, 워크플로우 조합, 실행 이력 조회.
- **원하는 모델 선택** — 모델 이름만 바꾸면 Anthropic / AWS Bedrock / 자체 호스팅 Ollama·vLLM 사이에서 자유롭게 전환.
- **1급 MCP 도구 통합** — MCP 서버를 등록하고 에이전트별로 사용 도구를 선택, 사용자별 자격증명을 Vault에서 주입.
- **에이전트 간 호출 (A2A)** — `@멘션`으로 에이전트가 다른 에이전트를 서브 도구처럼 호출, 서브 에이전트의 실행 내용이 부모 대화에 인라인 렌더링.
- **워크플로우** — [Temporal](https://temporal.io/) 위에서 에이전트와 결정적 스텝을 DAG로 엮어 실행; UI에서 재개·재생·조회.
- **기본적으로 안전** — 매 에이전트 턴이 [bubblewrap](https://github.com/containers/bubblewrap) 샌드박스 안에서 실행되며, 외부 통신은 환경별 Kubernetes NetworkPolicy로 제한.
- **멀티테넌트·유저 단위 격리** — OIDC 로그인, 사용자별 API 키·도구 자격증명을 Vault에 저장, 세션별 독립 워크스페이스.
- **선언적 인프라** — 런타임 환경이 Helm 릴리스로 관리; values 파일 하나로 새 환경(다른 이미지·다른 egress) 추가.

## 아키텍처

```
        ┌──────────────────────────────────────────────────────┐
        │                       Web UI                         │
        │     에이전트 · 워크플로우 · 채팅 · 실행 이력 · 관리      │
        └──────────────────────────┬───────────────────────────┘
                                   │ single origin
                                   │ (REST + WebSocket)
                  ┌────────────────▼────────────────┐
                  │   Edge proxy  (Caddy / ALB)     │
                  │   /api/* → API ·  /* → Web      │
                  └──────┬──────────────────┬───────┘
                         │                  │
        ┌────────────────▼───────┐  ┌───────▼─────────────────┐
        │        API 서버         │  │       Admin 콘솔        │
        │  인증 · CRUD · 채팅     │  │  에이전트 / 워크플로우    │
        │                         │  │  정의 관리              │
        └──────┬─────────────┬───┘  └─────────────────────────┘
               │             │
               │    ┌────────▼─────────────────────────────────┐
               │    │             플랫폼 서비스                 │
               │    │   LiteLLM Gateway                        │
               │    │    ├─ LLM 라우팅 (Anthropic / Bedrock /  │
               │    │    │   Ollama / vLLM …)                  │
               │    │    └─ MCP 통합 엔드포인트                 │
               │    │   Vault · Keycloak · Postgres · Redis    │
               │    │   Temporal · Prometheus · Grafana        │
               │    └──────────────────┬───────────────────────┘
               │                       │
        ┌──────▼───────────────────┐   │
        │    Agent Supervisor      │   │
        │  SSE 프록시 · abort ·    │   │
        │  메트릭                  │   │
        └──────────────┬───────────┘   │
                       │ HTTP          │
        ┌──────────────▼───────────────▼───────────────────────┐
        │              Agent Runtime Pool                      │
        │   Compose: in-stack `runtime` 컨테이너 (기본값)        │
        │   K8s   : 환경별 Helm 릴리스                          │
        │           • default — 제한된 egress, 기본 이미지      │
        │           • custom  — 오픈 인터넷 + 추가 툴링         │
        │   모든 pod는 agent-agnostic — 격리는 요청 단위의       │
        │   bubblewrap + 세션별 경로로 이루어집니다.             │
        └──────────────────────────────────────────────────────┘
```

## 컴포넌트

| 컴포넌트 | 역할 |
|----------|------|
| **Web UI** ([web/](web/)) | 사용자·운영자용 Next.js 프론트엔드. |
| **API 서버** ([api/](api/)) | OIDC 인증 기반 에이전트·세션·메시지·워크플로우 REST + WebSocket API. |
| **Admin 콘솔** ([admin/](admin/)) | 로컬 전용 운영자 UI (인증 없음). 에이전트·워크플로우 정의 관리. |
| **Agent Supervisor** ([agent-supervisor/](agent-supervisor/)) | 런타임에서 오는 출력을 스트리밍하고 Redis로 팬아웃, 사용자별 자격증명 주입, abort 처리. |
| **Workflow Worker** ([workflow-worker/](workflow-worker/)) | 워크플로우를 실행하는 Temporal worker. |
| **Agent Runtime** ([runtime/](runtime/)) | Node.js + [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-typescript) 기반 컨테이너로 실제 에이전트를 실행. compose 기본 런타임과 K8s 풀 이미지 모두에서 사용. |
| **LiteLLM Gateway** ([local-infra/config/litellm/](local-infra/config/litellm/)) | LLM 추론과 MCP 도구 호출의 단일 진입점. 모델 이름으로 라우팅하고 사용자별 시크릿 주입. |
| **Helm 차트** ([charts/](charts/)) | `aviary-platform` (namespace, baseline egress, 공유 워크스페이스 PVC, dev 전용 external-services 프록시), `aviary-environment` (런타임 풀 1개 = 릴리스 1개), 그리고 `api` / `admin` / `web` / `supervisor` / `workflow-worker` 서비스별 차트. |
| **공유 Python 패키지** ([shared/](shared/)) | API + Admin + Supervisor가 함께 쓰는 SQLAlchemy 모델·마이그레이션·OIDC 헬퍼. |

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| Web UI | Next.js, TypeScript, Tailwind CSS, shadcn/ui |
| API · Admin · Supervisor | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Agent Runtime | Node.js, [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-typescript), Claude Code CLI |
| 워크플로우 | [Temporal](https://temporal.io/) |
| LLM · MCP 게이트웨이 | [LiteLLM](https://github.com/BerriAI/litellm) |
| 인증 | OIDC (어떤 IdP든 가능; 로컬은 [Keycloak](https://www.keycloak.org/) 기본 제공) |
| 시크릿 | [HashiCorp Vault](https://www.vaultproject.io/) (개발용 vaultless 폴백 제공) |
| 데이터 | PostgreSQL, Redis |
| 관측 | OpenTelemetry, Prometheus, Grafana |
| 배포 | Helm + Kubernetes (로컬: K3s, 운영: EKS 등) |
| 샌드박스 | [bubblewrap](https://github.com/containers/bubblewrap), Kubernetes NetworkPolicy |

## 설치

### 사전 요구 사항

- `docker compose v2`가 포함된 Docker (Docker Desktop, OrbStack, Rancher Desktop 등)
- 이미지·볼륨용 디스크 공간 ~10 GB
- Linux / macOS / WSL2

### 저장소 구조 — 두 개의 compose 스택 + Helm

두 개의 compose 스택과 운영에 그대로 올라가는 Helm 차트로 구성됩니다:

| 스택 / 명령 | 포함 내용 | 소스 |
|-------------|-----------|------|
| `service` 그룹 | web, api, admin, supervisor, workflow-worker, **in-compose runtime**, edge Caddy proxy — 핫 리로드 dev 경로 | 프로젝트 루트 [compose.yml](compose.yml) |
| `infra` 그룹 | postgres, redis, temporal, temporal-ui, db-migrate, keycloak, vault, litellm, prometheus, grafana, otel-collector, 예제 MCP 서버, K3s 컨테이너, K3s용 Caddy proxy | [local-infra/compose.yml](local-infra/compose.yml) |
| `local-deploy.sh` | 운영 EKS와 동일한 차트들을 로컬 K3s 컨테이너에 적용 — 차트 검증 경로 | [scripts/local-deploy.sh](scripts/local-deploy.sh) + [charts/](charts/) |

`infra`는 필수입니다 (postgres / redis / temporal이 거기에 있음). `service`가 그 위에 사용자·운영자용 컴포넌트를 얹습니다. `local-deploy.sh`는 옵션입니다.

### 한 번에 기동

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh        # 빌드 + infra + service 기동
```

`setup-dev.sh`는 콤마로 구분된 부분 집합을 받습니다:

```bash
./scripts/setup-dev.sh infra                # 플랫폼 deps만 (postgres, redis, temporal, keycloak, …)
./scripts/setup-dev.sh infra,service        # 플랫폼 deps + 사용자·운영자용 서비스
./scripts/setup-dev.sh                      # 둘 다
```

스크립트는 `local-infra/.env`를 루트 `.env`로 심볼릭 링크한 뒤 각 그룹마다 `docker compose build` → `docker compose up -d`를 실행합니다. 재실행 시 볼륨은 보존됩니다.

운영 Helm 차트를 로컬 K3s에서 검증:

```bash
./scripts/local-deploy.sh setup                      # 모든 이미지 빌드, ctr import, helm apply
./scripts/local-deploy.sh setup --only=aviary-api    # 일부만 재빌드 + 재배포
./scripts/local-deploy.sh logs aviary-api            # 한 차트 로그 tail
./scripts/local-deploy.sh stop                       # 모든 플랫폼 deploy를 0으로 스케일
./scripts/local-deploy.sh clean                      # 모든 릴리스 helm-delete
```

`local-deploy.sh setup`은 K3s 컨테이너를 기동하고, api / supervisor / workflow-worker / runtime / web / db-migrate 이미지를 빌드해 containerd로 import한 뒤, 차트를 의존 순서로 적용합니다: `aviary-platform` → `aviary-api` (pre-install `db-migrate` Job 포함) → `aviary-supervisor` → `aviary-workflow-worker` → `aviary-env-{default,custom}` → `aviary-web`. 이미지 digest가 캐시되어 재실행 시 변경된 것만 다시 빌드합니다.

### 일상 운영 스크립트

```bash
./scripts/start-dev.sh  [groups]          # 정지된 compose 컨테이너 시작
./scripts/stop-dev.sh   [groups]          # compose 컨테이너 정지 (볼륨 유지)
./scripts/clean-dev.sh  [groups]          # compose 컨테이너 + 볼륨 모두 제거 (완전 초기화)
./scripts/logs.sh       {infra|service}   # 그룹 로그 tail

./scripts/local-deploy.sh {setup|start|stop|clean|logs}   # K8s 측
```

세부 반복 작업은 compose 스택을 직접 호출하면 됩니다:

```bash
docker compose up -d --build api                   # 루트 서비스 1개만 재빌드 + 재시작
docker compose restart supervisor                  # 빌드 없이 재시작
cd local-infra && docker compose restart litellm   # LiteLLM 패치/설정 변경 후
```

`api/`, `admin/`, `web/`, `agent-supervisor/`, `workflow-worker/`는 bind-mount되어 있어 대부분의 변경은 `--reload` / `npm run dev`로 핫 리로드됩니다 ([compose.override.yml](compose.override.yml) 참고).

## 사용 시나리오

`infra`는 모든 시나리오의 필수 조건입니다 (postgres / redis / temporal을 owning). 일상 핫 리로드 dev에서는 `service`를 추가하고, 차트 검증이 필요할 때 `local-deploy.sh`를 실행합니다.

### 시나리오 A — 최소 로컬 dev 스택

infra + service compose 기동. Supervisor는 in-compose `runtime`에 바로 붙고, LLM·MCP 호출은 [config.yaml](config.example.yaml)에 선언된 백엔드를 사용합니다.

```bash
cp config.example.yaml config.yaml          # 편집: llm_backends에 Anthropic API 키 등 추가
./scripts/setup-dev.sh                      # infra + service
```

Web UI를 열어 `dev-user`로 로그인 → 에이전트 생성 → 대화 시작. 엔드포인트는 아래 [서비스 엔드포인트](#서비스-엔드포인트) 참고.

### 시나리오 B — 실제 IdP / Vault / LiteLLM 연결

`infra`에 이미 Keycloak, Vault, LiteLLM, MCP, 관측이 모두 포함되어 있습니다. `.env`에 OIDC와 게이트웨이 변수를 설정 ([.env.example](.env.example) 참고)하고 `api`, `supervisor`를 재시작하면 됩니다 (`docker compose restart api supervisor`). 테스트 사용자 `user1@test.com` / `user2@test.com` (비밀번호 `password`)이 Keycloak realm에 시드되어 있습니다.

### 시나리오 C — 운영 Helm 차트를 로컬 K3s에서 검증

다음과 같은 경우 `local-deploy.sh`를 사용합니다:

- 환경별 egress 정책 (제한 vs. 오픈 인터넷),
- 환경별 커스텀 이미지 (추가 CLI, 언어 툴체인),
- 운영 EKS 배포의 사실적인 프리뷰 — web / api / supervisor / workflow-worker / runtime이 운영 GitOps 대상과 동일한 K3s 위에서 동작.

```bash
./scripts/setup-dev.sh infra              # postgres / redis / temporal / keycloak / litellm / vault
./scripts/local-deploy.sh setup           # web / api / supervisor / workflow-worker / runtime → K3s
```

두 개의 런타임 환경이 사전 구성되어 있습니다:

- **default** — 기본 `aviary-runtime` 이미지, 제한된 egress (DNS + 플랫폼만). NodePort `30300`.
- **custom** — `aviary-runtime-custom` 이미지 (기본 + 데모용 `cowsay`), `extraEgress: 0.0.0.0/0`. NodePort `30301`.

에이전트별 라우팅: Admin 콘솔에서 `agent.runtime_endpoint`를 `http://host.docker.internal:30300` (또는 `:30301`)로 지정하면 in-compose 런타임 대신 K8s 풀로 전송됩니다.

`local-deploy.sh`의 K3s용 Caddy 프록시(host port `:80`)와 service compose의 Caddy 프록시(host port `:3000`)는 서로 다른 포트를 사용해 동시 기동이 가능합니다. 같은 인프라(postgres/redis 등)를 공유한 채로 두 스택을 함께 띄울 경우, 앱 컴포넌트는 한쪽만 살려두세요 (`docker compose stop web api supervisor workflow-worker`로 service compose 쪽을 정지) — DB 동시 쓰기 경합을 막기 위함입니다.

### 시나리오 D — 단일 컴포넌트 반복 작업

```bash
# api/ 의 Python 코드 → 이미 핫 리로드. Dockerfile 변경 시:
docker compose up -d --build api

# LiteLLM 패치 변경 (local-infra/config/litellm/patches/*.py):
cd local-infra && docker compose restart litellm

# runtime/src/* 또는 Helm values 변경 → 이미지 재빌드 + 재배포 필요:
./scripts/local-deploy.sh setup --only=aviary-env-default
./scripts/local-deploy.sh setup --only=aviary-api    # 또는 다른 차트

# 반복 작업 중 로그 모니터링:
./scripts/logs.sh service                            # 루트 서비스 전체
./scripts/logs.sh infra                              # local-infra (litellm, keycloak, …)
./scripts/local-deploy.sh logs aviary-env-default    # K8s 런타임 pod
./scripts/local-deploy.sh logs aviary-api            # 다른 K8s deploy도 동일
```

### 시나리오 E — 일시 정지 / 재개 / 초기화

```bash
./scripts/stop-dev.sh                # 두 compose 그룹 정지; 볼륨 유지
./scripts/start-dev.sh               # 빌드 없이 재기동

./scripts/local-deploy.sh stop       # K8s deploy를 모두 0으로 스케일 (런타임 풀 포함)
./scripts/local-deploy.sh start      # 다시 1로 스케일

./scripts/clean-dev.sh service       # 앱 DB + Redis만 초기화 (Vault / Keycloak / K3s 상태는 유지)
./scripts/clean-dev.sh               # 두 compose 그룹 모두 초기화 (K3s 데이터 볼륨 포함)
./scripts/local-deploy.sh clean      # 모든 차트 릴리스 helm-delete (K3s 컨테이너는 유지)
```

## 서비스 엔드포인트

`setup-dev.sh` 완료 후 호스트에서 접근 가능한 URL입니다. 그룹별로 정리:

### `service` 그룹

| 서비스 | URL | 용도 |
|--------|-----|------|
| 브라우저 진입점 (Caddy proxy) | http://localhost:3000 | `/api/*` → API · `/` → Web — 운영 ALB와 동일한 모양 |
| Admin 콘솔 | http://localhost:8001 | 운영자 UI (인증 없음, 로컬 전용) |

API와 Supervisor는 compose 내부 DNS(`api:8000` / `supervisor:9000`)로만 노출됩니다. 호스트로는 publish하지 않으니 `docker compose exec`로 들어가거나 Caddy 프록시를 통해 접근하세요.

### `infra` 그룹

| 서비스 | URL | 로그인 / 용도 |
|--------|-----|--------------|
| Postgres | localhost:5432 | 앱 + LiteLLM + Keycloak + Temporal DB |
| Redis | localhost:6379 | Pub/sub, unread 카운터 |
| Temporal | localhost:7233 | gRPC (worker가 연결) |
| Temporal UI | http://localhost:8233 | 워크플로우 인스펙터 |
| Keycloak | http://localhost:8080 | `admin` / `admin` |
| Vault | http://localhost:8200 | 토큰: `dev-root-token` |
| LiteLLM Proxy | http://localhost:8090 | 마스터 키 `sk-aviary-dev` |
| LiteLLM UI | http://localhost:8090/ui | `admin` / `admin` |
| LiteLLM MCP 엔드포인트 | http://localhost:8090/mcp | 통합 MCP |
| Grafana | http://localhost:3001 | 익명 admin; Aviary Supervisor 대시보드 자동 프로비저닝 |
| Prometheus | http://localhost:9090 | — |
| OTel Collector | localhost:4317 (gRPC) / 4318 (HTTP) | OTLP 수신기 |

테스트 계정 (Keycloak realm `aviary`): `user1@test.com`, `user2@test.com`, 비밀번호 `password`.

### `local-deploy.sh` (K3s)

`./scripts/local-deploy.sh setup` 완료 후, 클러스터 외부의 Caddy 프록시(`local-infra/compose.yml`의 `proxy-k3s`)가 K3s NodePort 앞에 위치합니다 — 운영 ALB와 동일한 역할입니다.

| 엔드포인트 | 차트 / 용도 |
|-----------|------------|
| http://localhost | Caddy 프록시 → `aviary-web` + `/api/*` → `aviary-api` (단일 브라우저 진입점) |
| http://localhost:30300 | `aviary-env-default` 런타임 풀 |
| http://localhost:30301 | `aviary-env-custom` 런타임 풀 |
| 컨테이너 경유 `kubectl` | `cd local-infra && docker compose --profile k3s exec k8s kubectl …` |

`aviary-admin`과 `aviary-supervisor`는 ClusterIP 전용 — `kubectl port-forward -n platform svc/aviary-admin 8001:8001` (또는 `svc/aviary-supervisor 9000:9000`)으로 접근하세요. web/api NodePort(31301/31000)는 프록시의 upstream이지 브라우저용이 아닙니다. Postgres / Redis / Temporal / Keycloak / Vault / LiteLLM은 compose에 그대로 두고 `aviary-platform`의 external-services 프록시로 클러스터에 노출됩니다.

## 설정

- **단일 .env** — 두 compose 스택이 프로젝트 루트의 [.env](.env.example)를 공유; `local-infra/.env`는 자동으로 심볼릭 링크됩니다.
- **`config.yaml`** — LLM 백엔드, MCP 서버, 그리고 (vaultless 개발 모드에서) 사용자별 시크릿을 선언. `VAULT_ADDR` / `VAULT_TOKEN` 및 `LLM_GATEWAY_URL` / `MCP_GATEWAY_URL`이 unset일 때 사용. [config.example.yaml](config.example.yaml)에서 시작.
- **LiteLLM** — 모델 라우팅과 플랫폼 공용 MCP 서버는 [local-infra/config/litellm/config.yaml](local-infra/config/litellm/config.yaml); 서버별 Vault 키 매핑은 [mcp-secret-injection.yaml](local-infra/config/litellm/mcp-secret-injection.yaml).
- **런타임 환경** — 환경 1개 = `charts/aviary-environment` Helm 릴리스 1개. `values-*.yaml`을 복제해서 `image`, `extraEgress`, 리소스 limit 등을 지정한 뒤 `./scripts/local-deploy.sh setup --only=aviary-env-<name>`로 적용.
- **Egress 정책** — `charts/aviary-platform`의 baseline `NetworkPolicy`가 항상 적용되며, 환경별 `extraEgress`가 그 위에 union됩니다.
- **시크릿** — 사용자별 자격증명은 Vault의 `secret/aviary/credentials/{user_sub}/{namespace}/{key}`에 저장 (vaultless 폴백 시 `config.yaml`의 `secrets:` 블록).

## 테스트

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
cd agent-supervisor && uv run pytest tests/ -v
```

API/Admin 테스트는 `aviary_test` 전용 Postgres DB와 `NullPool`을 사용하며 lifespan 없이 동작합니다.

## 배포

같은 Helm 차트가 로컬 K3s와 운영 클러스터에서 동일하게 동작합니다. 운영 전환은 주로 다음 작업입니다:

- `aviary-platform`의 공유 워크스페이스 PVC를 운영용 RWX `StorageClass`로 전환 (예: AWS EFS),
- 예제 Keycloak realm과 Vault 부트스트랩을 조직의 IdP·시크릿 저장소로 교체,
- 운영용 모델 자격증명과 MCP 서버 설정 공급,
- Web · API · LiteLLM을 조직의 ingress로 노출.

## 라이선스

[LICENSE](./LICENSE) 파일을 참고하세요.
