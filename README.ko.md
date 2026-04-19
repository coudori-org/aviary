# Aviary

**AI 에이전트를 만들고 운영하고 오케스트레이션하는 셀프 호스팅 플랫폼.**

[English](./README.md)

Aviary는 조직 내부에서 AI 에이전트를 직접 빌드·운영하고 싶은 팀을 위한 오픈소스 멀티테넌트 플랫폼입니다. 웹 UI에서 에이전트를 생성하고, instruction과 도구([MCP](https://modelcontextprotocol.io/) 서버 포함)를 지정하고, 모델을 고른 뒤 바로 대화할 수 있습니다. 여러 에이전트를 워크플로우로 엮어서 실행할 수도 있습니다. 에이전트는 샌드박스와 네트워크 정책으로 격리된 런타임에서 동작하기 때문에, 코드·데이터·인터넷을 다루게 해도 안전합니다.

Aviary는 기존 조직 환경에 그대로 얹혀 쓰도록 설계되었습니다 — 사내 IdP(OIDC), 시크릿 저장소(Vault), 모델 공급자(Anthropic / AWS Bedrock / 자체 호스팅 Ollama·vLLM), Kubernetes 클러스터와 직접 연동됩니다.

## 핵심 기능

- **전체 라이프사이클을 한 웹 UI에서** — 에이전트를 탐색·생성·설정·대화·삭제하고, 워크플로우로 조합하고, 지난 실행 이력을 조회합니다.
- **원하는 모델 선택** — 모델 이름만 바꾸면 Anthropic / AWS Bedrock / 자체 호스팅 Ollama·vLLM 사이에서 자유롭게 전환됩니다.
- **1급 MCP 도구 통합** — MCP 서버를 연결하고, 각 에이전트가 쓸 수 있는 도구를 선택하고, 사용자별 자격증명을 Vault에서 주입해 시크릿 노출 없이 도구 호출을 인증합니다.
- **에이전트 간 호출 (A2A)** — `@멘션`으로 에이전트가 다른 에이전트를 서브 도구처럼 호출할 수 있고, 서브 에이전트의 실행 내용이 부모 대화에 인라인으로 렌더링됩니다.
- **워크플로우** — 에이전트와 결정적(deterministic) 스텝을 DAG로 엮어 신뢰성 있는 워크플로우 엔진 위에서 실행; UI에서 재개·재생·조회가 가능합니다.
- **기본적으로 안전** — 매 에이전트 턴이 [bubblewrap](https://github.com/containers/bubblewrap) 샌드박스 안에서 자체 마운트·PID·네트워크 뷰로 실행되며, 외부 통신은 환경별 Kubernetes NetworkPolicy로 제한됩니다.
- **멀티테넌트·유저 단위 격리** — OIDC 로그인, 사용자별 API 키·도구 자격증명을 Vault에 저장, 세션별 독립 워크스페이스 제공.
- **선언적 인프라** — 런타임 환경이 Helm 릴리스로 관리됩니다. 새로운 환경(다른 이미지, 다른 egress 정책, 다른 모델 풀)을 만들려면 values 파일 하나만 적용하면 됩니다.
- **운영 준비 완료** — Prometheus 메트릭과 프로비저닝된 Grafana 대시보드, 구조화 로그, 사용자가 취소하면 진행 중인 스트림을 깔끔히 중단하는 Supervisor를 기본 제공.
- **로컬 환경은 단일 명령으로** — 스크립트 한 번이면 이미지 빌드, Helm 차트 적용, 모든 서비스 기동이 끝납니다.

## 아키텍처

```
        ┌──────────────────────────────────────────────────────┐
        │                       Web UI                         │
        │    에이전트 · 워크플로우 · 채팅 · 실행 이력 · 관리     │
        └──────────────┬─────────────────────┬─────────────────┘
                       │ REST + WebSocket    │
        ┌──────────────▼─────────┐   ┌───────▼─────────────────┐
        │        API 서버         │   │       Admin 콘솔        │
        │  인증 · CRUD · 채팅     │   │  에이전트 / 도구 /       │
        │  워크플로우 제어         │   │      시크릿 관리         │
        └──────┬─────────────┬───┘   └─────────────┬───────────┘
               │             │                     │
               │    ┌────────▼─────────────────────▼──────────┐
               │    │             플랫폼 서비스                 │
               │    │                                          │
               │    │   LiteLLM Gateway                        │
               │    │    ├─ LLM 라우팅 (Anthropic, Bedrock,    │
               │    │    │   Ollama, vLLM, …)                  │
               │    │    └─ MCP 통합 엔드포인트                 │
               │    │                                          │
               │    │   Vault · Keycloak · Postgres · Redis    │
               │    │   Prometheus · Grafana                   │
               │    └──────────────────┬───────────────────────┘
               │                       │
        ┌──────▼───────────────────┐   │
        │    Agent Supervisor      │   │
        │  에이전트 출력 스트리밍,   │   │
        │  abort 처리, 메트릭 발행  │   │
        └──────────────┬───────────┘   │
                       │ HTTP          │
        ┌──────────────▼───────────────▼───────────────────────┐
        │                  Kubernetes 클러스터                   │
        │                                                      │
        │   런타임 환경 (Helm 릴리스):                          │
        │     • default  — 제한된 egress, 기본 이미지           │
        │     • custom   — 오픈 인터넷 + 추가 툴링              │
        │     • …원하는 환경을 직접 추가                        │
        │                                                      │
        │   환경 = Deployment + Service,                        │
        │   클러스터 공유 워크스페이스 볼륨을 함께 마운트.        │
        │   모든 pod는 agent-agnostic — 격리는 요청 단위의       │
        │   bubblewrap + 세션별 경로로 이루어집니다.             │
        └──────────────────────────────────────────────────────┘
```

### 컴포넌트 역할

- **Web UI** — 사용자와 운영자를 위한 Next.js 프론트엔드.
- **API 서버** — OIDC 인증 기반의 에이전트·세션·메시지·워크플로우 REST + WebSocket API.
- **Admin 콘솔** — 에이전트 정의, MCP 서버 등록, 사용자별 자격증명 관리를 위한 운영자 UI.
- **Agent Supervisor** — 런타임 풀에서 오는 에이전트 출력을 스트리밍하고, 클라이언트에 이벤트를 팬아웃하며, 사용자의 abort 요청 시 진행 중인 실행을 취소합니다.
- **LiteLLM Gateway** — LLM 추론과 MCP 도구 호출의 단일 진입점. 모델 이름으로 라우팅하고 사용자별 자격증명을 주입합니다.
- **Agent Runtime** — 실제로 에이전트를 실행하는 pod 풀. 모든 pod가 모든 에이전트를 서빙하며, 요청 단위 샌드박싱은 커널 수준에서 이루어집니다.
- **공유 워크스페이스 볼륨** — 각 세션의 파일이 저장되는 클러스터 공유 볼륨. 같은 세션의 에이전트들은 파일을 주고받을 수 있지만, 세션 간에는 서로 보이지 않습니다.
- **플랫폼 서비스** — Postgres(애플리케이션 상태), Redis(pub/sub + 캐시), Keycloak(인증), Vault(시크릿), Prometheus + Grafana(관측).

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| Web UI | Next.js, TypeScript, Tailwind CSS, shadcn/ui |
| API · Admin | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| 에이전트 런타임 | Node.js, [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-typescript), Claude Code CLI |
| Agent Supervisor | Python, FastAPI, Redis, Prometheus client |
| 워크플로우 | [Temporal](https://temporal.io/) |
| LLM · MCP 게이트웨이 | [LiteLLM](https://github.com/BerriAI/litellm) |
| 인증 | [Keycloak](https://www.keycloak.org/) (OIDC) |
| 시크릿 | [HashiCorp Vault](https://www.vaultproject.io/) |
| 데이터 | PostgreSQL, Redis |
| 관측 | Prometheus, Grafana |
| 배포 | Helm, Kubernetes (로컬: K3s, 운영: EKS) |
| 샌드박스 | [bubblewrap](https://github.com/containers/bubblewrap), Kubernetes NetworkPolicy |

## 시작하기

**사전 요구 사항:** Docker Desktop (또는 동등한 컨테이너 런타임).

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh
```

이 명령 하나로 모든 이미지 빌드, 서비스 기동, DB 마이그레이션, 런타임 환경을 정의하는 Helm 차트 설치까지 끝납니다.

스크립트가 끝난 뒤 접근 가능한 서비스:

| 서비스 | URL |
|--------|-----|
| Web UI | http://localhost:3000 |
| API 서버 | http://localhost:8000 |
| Admin 콘솔 | http://localhost:8001 |
| LiteLLM Proxy / UI | http://localhost:8090 · http://localhost:8090/ui |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| Keycloak | http://localhost:8080 |

테스트 계정: `user1@test.com`, `user2@test.com` (비밀번호: `password`).

일상 운영 명령:

```bash
docker compose up -d          # 시작
docker compose down           # 중지 (데이터 유지)
docker compose down -v        # 전체 초기화 (데이터 포함)
```

소스 코드가 bind-mount되어 있어 `api/`, `admin/`, `web/` 변경은 핫 리로드로 반영됩니다.

## 사용 흐름

1. 테스트 계정으로 Web UI에 **로그인**합니다.
2. 에이전트를 **생성**합니다 — 이름, instruction, 모델을 지정하고 필요 시 MCP 도구와 다른 에이전트(A2A 용)를 연결합니다.
3. 에이전트와 **대화**합니다. 응답은 실시간 스트리밍되며, *Stop* 버튼으로 언제든 중단할 수 있습니다.
4. 에이전트 호출과 결정적 스텝을 엮어 **워크플로우**를 구성하고 UI 또는 API에서 실행합니다.
5. Grafana로 활동을 **모니터링**하고, Admin 콘솔에서 에이전트·MCP 서버·사용자 자격증명을 관리합니다.

## 프로젝트 구조

```
aviary/
├── web/                  # Next.js Web UI
├── api/                  # API 서버 (사용자 대면)
├── admin/                # Admin 콘솔 (운영자 대면)
├── runtime/              # 에이전트 런타임 (풀 멤버)
├── agent-supervisor/     # SSE 프록시 + Prometheus 메트릭
├── shared/               # 공유 Python 패키지 (모델, 마이그레이션, OIDC)
├── mcp-servers/          # 예제 MCP 서버 구현
├── charts/
│   ├── aviary-platform/       # 클러스터 전역 리소스 (namespace, baseline egress, 공유 워크스페이스)
│   └── aviary-environment/    # 릴리스 하나 = 런타임 환경 하나
├── config/               # LiteLLM, Keycloak, 관측 설정
├── scripts/              # 설치·유틸 스크립트
└── docker-compose.yml
```

## 설정

대부분의 설정은 `docker-compose.yml`, `charts/` 하위의 Helm `values-*.yaml`, `config/` 디렉터리에 있습니다. 주요 포인트:

- **모델 라우팅** — `config/litellm/config.yaml`이 모델 이름별로 어떤 LLM 백엔드로 전달할지를 정의합니다.
- **MCP 서버** — 플랫폼 공용 MCP 서버는 `config/litellm/config.yaml`에 선언하고, 추가 서버는 운영자가 Admin 콘솔에서 런타임에 등록할 수 있습니다.
- **런타임 환경** — 환경 하나 = `charts/aviary-environment`의 Helm 릴리스 하나. 각 환경이 자체 이미지·egress 규칙·리소스 제한을 갖습니다. values 파일을 복제해 적용하면 새 환경이 만들어집니다.
- **Egress 정책** — `charts/aviary-platform`이 기본 `NetworkPolicy`를 항상 적용하며, 환경별 규칙이 그 위에 union됩니다.
- **시크릿** — 사용자별 자격증명(모델 API 키, 도구 토큰)은 Vault의 사용자별 경로에 저장되고, 런타임 pod가 아니라 게이트웨이에서 주입됩니다.

## 테스트

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
cd agent-supervisor && uv run pytest tests/ -v
```

## 배포

같은 Helm 차트가 로컬 K3s와 운영 클러스터에서 동일하게 동작합니다. 운영 전환은 주로 다음 작업으로 구성됩니다:

- 공유 워크스페이스 볼륨을 운영용 `StorageClass`(예: AWS의 EFS)로 전환,
- 예제 Keycloak 렐름과 Vault 부트스트랩을 조직의 IdP·시크릿 저장소로 교체,
- 운영용 모델 자격증명과 MCP 서버 설정 공급,
- Web UI · API · LiteLLM을 원하는 ingress로 노출.

## 라이선스

[LICENSE](./LICENSE) 파일을 참고하세요.
