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
        └──────────────┬─────────────────────┬─────────────────┘
                       │ REST + WebSocket    │
        ┌──────────────▼─────────┐   ┌───────▼─────────────────┐
        │        API 서버         │   │       Admin 콘솔        │
        │  인증 · CRUD · 채팅     │   │  에이전트 / 워크플로우    │
        │                         │   │  정의 관리              │
        └──────┬─────────────┬───┘   └─────────────────────────┘
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
| **Helm 차트** ([charts/](charts/)) | `aviary-platform` (클러스터 전역: namespace, baseline egress, 공유 워크스페이스 PVC) + `aviary-environment` (런타임 환경 1개 = 릴리스 1개). |
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

### 저장소 구조 — 두 개의 compose 스택

저장소는 두 개의 compose 스택과 Helm 차트로 구성되며, 모든 구성 요소가 세 개의 그룹으로 묶여 있습니다:

| 그룹 | 포함 서비스 | 스택 |
|------|-------------|------|
| `service` | api, admin, web, supervisor, workflow-worker, **in-compose runtime**, postgres, redis, temporal, temporal-ui | 프로젝트 루트 [compose.yml](compose.yml) |
| `infra` | keycloak, vault, litellm, prometheus, grafana, otel-collector, 예제 MCP 서버 (jira, confluence) | [local-infra/compose.yml](local-infra/compose.yml) |
| `runtime` | K3s + `aviary-environment` Helm 릴리스 (`default`, `custom`) — 환경별 샌드박스 런타임 풀 | [local-infra/compose.yml](local-infra/compose.yml) (`k3s` 프로필) + [charts/](charts/) |

`service` 스택만으로도 에이전트와 end-to-end로 대화할 수 있습니다. `infra`와 `runtime`은 옵션입니다.

### 한 번에 기동

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh        # 세 그룹 모두 빌드 + 기동
```

`setup-dev.sh`는 콤마로 구분된 부분 집합을 받습니다:

```bash
./scripts/setup-dev.sh service              # 서비스만 — 가장 빠른 경로
./scripts/setup-dev.sh service,infra        # 서비스 + IdP/Vault/LiteLLM/관측
./scripts/setup-dev.sh runtime              # 런타임 이미지 (재)빌드, helm apply, rollout
./scripts/setup-dev.sh                      # 전체
```

스크립트가 하는 일:

1. `local-infra/.env`를 루트 `.env`로 심볼릭 링크 (단일 진실 공급원).
2. `service` / `infra`: `docker compose build` → `docker compose up -d`.
3. `runtime`: K3s 기동, `aviary-runtime:latest`와 `aviary-runtime-custom:latest` 빌드 후 K3s containerd로 import, `aviary-platform`과 두 `aviary-environment` 릴리스를 `alpine/helm template | kubectl apply -f -`로 적용, rollout 대기.

재실행 시 볼륨은 보존됩니다.

### 일상 운영 스크립트

모든 스크립트는 동일한 `[그룹|csv]` 인자를 받습니다. 인자가 없으면 모든 그룹.

```bash
./scripts/start-dev.sh  [groups]          # 정지된 컨테이너 시작 / 런타임을 다시 1로 스케일
./scripts/stop-dev.sh   [groups]          # 컨테이너 정지 / 런타임 0으로 스케일 (볼륨 유지)
./scripts/clean-dev.sh  [groups]          # 컨테이너 + 볼륨 모두 제거 (완전 초기화)
./scripts/logs.sh       {infra|runtime|service}   # 그룹별 로그 tail
```

세부 반복 작업은 compose 스택을 직접 호출하면 됩니다:

```bash
docker compose up -d --build api                   # 루트 서비스 1개만 재빌드 + 재시작
docker compose restart supervisor                  # 빌드 없이 재시작
cd local-infra && docker compose restart litellm   # LiteLLM 패치/설정 변경 후
```

`api/`, `admin/`, `web/`, `agent-supervisor/`, `workflow-worker/`는 bind-mount되어 있어 대부분의 변경은 `--reload` / `npm run dev`로 핫 리로드됩니다 ([compose.override.yml](compose.override.yml) 참고).

## 사용 시나리오

가장 작은 그룹 조합으로 시작하세요. 나중에 `infra`나 `runtime`을 추가해도 페널티가 없습니다.

### 시나리오 A — 그냥 한 번 써보기 (가장 빠른 경로, ~2분)

`service` 그룹만 사용. IdP·Vault·LiteLLM·K8s 없이 동작합니다. Supervisor는 in-compose `runtime` 컨테이너에 바로 붙고, LLM·MCP 호출은 [config.yaml](config.example.yaml)에 선언된 `llm_backends` / `mcp_servers`를 사용합니다.

```bash
cp config.example.yaml config.yaml          # 편집: llm_backends에 Anthropic API 키 등 추가
./scripts/setup-dev.sh service
```

Web UI를 열어 `dev-user`로 로그인 → 에이전트 생성 → 대화 시작. 엔드포인트는 아래 [서비스 엔드포인트](#서비스-엔드포인트) 참고.

### 시나리오 B — 풀 로컬 스택 (실제 OIDC, Vault, LiteLLM, MCP, 관측)

`infra` 그룹을 추가합니다. 이제 Keycloak이 JWT를 검증하고, Vault가 사용자별 자격증명을 보관하고, LiteLLM이 LLM + MCP를 통합하고, Grafana에 supervisor 대시보드가 뜨고, 번들된 `mcp-jira` / `mcp-confluence` 예제도 사용 가능합니다.

```bash
./scripts/setup-dev.sh service,infra
```

`.env`에 OIDC와 게이트웨이 변수를 설정 (Keycloak issuer + LiteLLM URL — [.env.example](.env.example) 참고)하고 `api`, `supervisor`를 재시작하세요. 테스트 사용자 `user1@test.com` / `user2@test.com` (비밀번호 `password`)이 Keycloak realm에 시드되어 있습니다.

### 시나리오 C — 환경별 샌드박스 런타임 풀 (K8s)

다음과 같은 경우 `runtime` 그룹을 추가합니다:

- 환경별 egress 정책 (제한 vs. 오픈 인터넷),
- 환경별 커스텀 이미지 (추가 CLI, 언어 툴체인),
- 운영 K8s 배포의 사실적인 프리뷰.

```bash
./scripts/setup-dev.sh                       # 세 그룹 모두
# 또는 기존 service+infra 위에 추가:
./scripts/setup-dev.sh runtime
```

두 개의 런타임 환경이 사전 구성되어 있습니다:

- **default** — 기본 `aviary-runtime` 이미지, 제한된 egress (DNS + 플랫폼만). NodePort `30300`.
- **custom** — `aviary-runtime-custom` 이미지 (기본 + 데모용 `cowsay`), `extraEgress: 0.0.0.0/0`. NodePort `30301`.

에이전트별 라우팅: Admin 콘솔에서 `agent.runtime_endpoint`를 `http://host.docker.internal:30300` (또는 `:30301`)로 지정하면 in-compose 런타임 대신 K8s 풀로 전송됩니다.

### 시나리오 D — 단일 컴포넌트 반복 작업

```bash
# api/ 의 Python 코드 → 이미 핫 리로드. Dockerfile 변경 시:
docker compose up -d --build api

# LiteLLM 패치 변경 (local-infra/config/litellm/patches/*.py):
cd local-infra && docker compose restart litellm

# runtime/src/* 또는 Helm values 변경 → 이미지 재빌드 + 재배포 필요:
./scripts/setup-dev.sh runtime

# 반복 작업 중 로그 모니터링:
./scripts/logs.sh service       # 루트 서비스 전체
./scripts/logs.sh infra         # local-infra (litellm, keycloak, …)
./scripts/logs.sh runtime       # K8s 런타임 pod
```

### 시나리오 E — 일시 정지 / 재개 / 초기화

```bash
./scripts/stop-dev.sh                # 모두 정지; 볼륨 (DB, Vault, 워크스페이스) 유지
./scripts/start-dev.sh               # 빌드 없이 재기동

./scripts/stop-dev.sh runtime        # 런타임 풀만 0으로 스케일 (배터리 절약)
./scripts/start-dev.sh runtime

./scripts/clean-dev.sh service       # 앱 DB + Redis만 초기화 (Vault / Keycloak / K3s 상태는 유지)
./scripts/clean-dev.sh               # 모두 초기화 — 완전 리셋
```

## 서비스 엔드포인트

`setup-dev.sh` 완료 후 호스트에서 접근 가능한 URL입니다. 그룹별로 정리:

### `service` 그룹

| 서비스 | URL | 용도 |
|--------|-----|------|
| Web UI | http://localhost:3000 | 사용자 앱 |
| API 서버 | http://localhost:8000 | REST + WebSocket |
| Admin 콘솔 | http://localhost:8001 | 운영자 UI (인증 없음, 로컬 전용) |
| Agent Supervisor | http://localhost:9000 | Bearer 인증; 스트리밍 프록시 |
| Temporal UI | http://localhost:8233 | 워크플로우 인스펙터 |
| Postgres | localhost:5432 | 앱 + LiteLLM DB |
| Redis | localhost:6379 | Pub/sub, unread 카운터 |
| Temporal | localhost:7233 | gRPC (worker가 연결) |

### `infra` 그룹

| 서비스 | URL | 로그인 |
|--------|-----|--------|
| Keycloak | http://localhost:8080 | `admin` / `admin` |
| Vault | http://localhost:8200 | 토큰: `aviary-dev-token` |
| LiteLLM Proxy | http://localhost:8090 | 마스터 키 `sk-aviary-dev` |
| LiteLLM UI | http://localhost:8090/ui | `admin` / `admin` |
| LiteLLM MCP 엔드포인트 | http://localhost:8090/mcp | 통합 MCP |
| Grafana | http://localhost:3001 | 익명 admin; Aviary Supervisor 대시보드 자동 프로비저닝 |
| Prometheus | http://localhost:9090 | — |
| OTel Collector | localhost:4317 (gRPC) / 4318 (HTTP) | OTLP 수신기 |

테스트 계정 (Keycloak realm `aviary`): `user1@test.com`, `user2@test.com`, 비밀번호 `password`.

### `runtime` 그룹

| 엔드포인트 | 용도 |
|-----------|------|
| http://localhost:30300 | `aviary-env-default` 런타임 풀 (NodePort) |
| http://localhost:30301 | `aviary-env-custom` 런타임 풀 (NodePort) |
| 컨테이너 경유 `kubectl` | `cd local-infra && docker compose --profile k3s exec k8s kubectl …` |

## 설정

- **단일 .env** — 두 compose 스택이 프로젝트 루트의 [.env](.env.example)를 공유; `local-infra/.env`는 자동으로 심볼릭 링크됩니다.
- **`config.yaml`** — LLM 백엔드, MCP 서버, 그리고 (vaultless 개발 모드에서) 사용자별 시크릿을 선언. `VAULT_ADDR` / `VAULT_TOKEN` 및 `LLM_GATEWAY_URL` / `MCP_GATEWAY_URL`이 unset일 때 사용. [config.example.yaml](config.example.yaml)에서 시작.
- **LiteLLM** — 모델 라우팅과 플랫폼 공용 MCP 서버는 [local-infra/config/litellm/config.yaml](local-infra/config/litellm/config.yaml); 서버별 Vault 키 매핑은 [mcp-secret-injection.yaml](local-infra/config/litellm/mcp-secret-injection.yaml).
- **런타임 환경** — 환경 1개 = `charts/aviary-environment` Helm 릴리스 1개. `values-*.yaml`을 복제해서 `image`, `extraEgress`, 리소스 limit 등을 지정한 뒤 `./scripts/setup-dev.sh runtime` 재실행.
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
- Web UI · API · LiteLLM을 원하는 ingress로 노출.

## 라이선스

[LICENSE](./LICENSE) 파일을 참고하세요.
