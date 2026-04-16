# Aviary

**멀티테넌트 AI 에이전트 플랫폼**

[English](./README.md)

Aviary는 웹 UI로 AI 에이전트를 생성·설정·사용하는 엔터프라이즈 플랫폼입니다. 런타임 환경은 Helm 릴리스로 Kubernetes 클러스터에 선언적으로 프로비저닝되고(환경 당 Deployment 풀 하나), 그 외의 모든 서비스 — API, Admin 콘솔, Agent Supervisor — 는 일반 배포 단위(로컬은 docker-compose, 운영은 플랫폼 표준 배포)를 따릅니다. 에이전트는 커널 수준 bubblewrap과 네트워크 수준 baseline NetworkPolicy + 선택적 환경별 규칙으로 격리됩니다.

## 아키텍처

```
┌────────────────────────────────────────────────────────────────┐
│                        Web UI (Next.js)                        │
│      에이전트 카탈로그 · 생성/편집 · 채팅 세션 · ACL 설정       │
└───────────────┬────────────────────────────────────────────────┘
                │ REST + WebSocket
┌───────────────▼────────────────────────────────────────────────┐
│                      API 서버 (FastAPI)                         │
│   OIDC 인증 · Agent CRUD · 세션 관리 · ACL · A2A                │
│   (agent.runtime_endpoint를 조회해 supervisor에 전달)            │
└───┬───────────┬────────────────────────────────────────────────┘
    │           │                           ┌────────────────────┐
    │           │                           │  Admin 콘솔         │
    │           │                           │  에이전트 설정 +    │
    │           │                           │  runtime_endpoint   │
    │           │                           │  오버라이드         │
    │           │                           └──────────┬─────────┘
    │   ┌───────▼────────────────────────────────────┐ │
    │   │              플랫폼 서비스                   │ │
    │   │                                            │ │
    │   │  ┌─────────────────┐                       │ │
    │   │  │ LiteLLM Gateway │◀── Vault              │ │
    │   │  │ (모델 라우팅,    │    (유저별 API 키)    │ │
    │   │  │  API 키 주입)    │                       │ │
    │   │  └────────┬────────┘                       │ │
    │   │     ┌─────┴───────────────────┐            │ │
    │   │     ▼            ▼            ▼            │ │
    │   │  Claude API   Ollama/vLLM   Bedrock        │ │
    │   │                                            │ │
    │   │  ┌─────────────────────────────────────┐   │ │
    │   │  │ MCP Gateway                         │◀──┴ Vault
    │   │  │ (도구 카탈로그, ACL, 프록시,          │     (도구 자격증명)
    │   │  │  OIDC 인증, 자동 디스커버리)          │     │
    │   │  └────────┬────────────────────────────┘     │
    │   │           ▼                                   │
    │   │     백엔드 MCP 서버                            │
    │   └──────────────────────────────────────────────┘
    │
    │   ┌────────────────────────────────────────────────────────┐
    │   │   Agent Supervisor (docker-compose, K8s 밖)             │
    │   │     SSE reverse proxy · Redis publish · 조립            │
    │   │     in-memory abort registry · /metrics                 │
    │   │     (호출자가 runtime_endpoint를 body로 전달)            │
    │   └───────────────────────┬────────────────────────────────┘
    │                           │ HTTP via env Service (dev: NodePort / prod: ClusterIP)
    │   ┌───────────────────────▼────────────────────────────────┐
    │   │                  Kubernetes 클러스터                      │
    │   │             (로컬: K3s · 운영: EKS · Helm으로 통일)        │
    │   │                                                        │
    │   │  ┌─── NS: agents ────────────────────────────────────┐ │
    │   │  │ baseline NetworkPolicy                            │ │
    │   │  │   (DNS + platform + LiteLLM + MCP GW + API)       │ │
    │   │  │                                                   │ │
    │   │  │ 환경 릴리스: aviary-env-default                    │ │
    │   │  │   Deployment (replicas ≥ 1) · Service · RWX PVC   │ │
    │   │  │   풀이 모든 에이전트를 서빙                         │ │
    │   │  │   bwrap 샌드박스 · 세션 공유 디렉토리 ·             │ │
    │   │  │   (agent, session)별 .claude / .venv               │ │
    │   │  │                                                   │ │
    │   │  │ 환경 릴리스: aviary-env-custom-* (선택)            │ │
    │   │  │   동일 형태 + extraEgress (별도 풀)                │ │
    │   │  └───────────────────────────────────────────────────┘ │
    │   └─────────────────────────────────────────────────────────┘
    │
    └─▶ PostgreSQL · Redis · Keycloak · Vault
```

## 주요 기능

- **사전 프로비저닝된 런타임 환경** — `charts/aviary-environment` Helm 릴리스가 런타임 풀을 선언적으로 구성. 에이전트별 Deployment 없음, cold start 없음. 환경은 항상 켜져 있음.
- **Supervisor는 K8s 밖** — Agent Supervisor는 API/Admin과 동일한 배포 단위(dev: docker-compose)로 구성. runtime endpoint는 Service로 접근. K8s 범위는 runtime pool에만 국한 (GitOps 범위 = K8s 범위).
- **연결-닫힘 기반 Abort** — Supervisor는 활성 publish task를 in-memory registry로 관리. abort = task cancel → httpx 컨텍스트 종료 → Service로 pinned된 TCP close → runtime pod의 close handler 발동 → SDK abort. pod IP 추적, Redis 신호, runtime의 Redis 의존 모두 불필요.
- **에이전트별 엔드포인트 오버라이드** — 기본적으로 모든 에이전트가 default 환경을 공유. Admin 콘솔에서 에이전트의 `runtime_endpoint`를 설정해 전용 환경(예: GPU 풀, 격리 SG)으로 라우팅 — 코드 변경·마이그레이션 없음.
- **Agent-agnostic 런타임 풀** — 환경 내 모든 pod가 모든 에이전트를 서빙. `agent_id`는 매 요청 `agent_config`로 전달. 격리는 디스크 경로(`sessions/{sid}/agents/{aid}/…`) + bubblewrap이 담당.
- **bubblewrap 세션 격리** — 각 요청이 커널 수준 마운트 네임스페이스에서 실행. 같은 세션의 에이전트들은 `/workspace`를 공유(A2A), `.claude/`와 `.venv/`는 (agent, session)별.
- **에이전트 간 호출 (A2A)** — instruction이나 채팅에서 `@멘션`으로 서브 에이전트 호출; 서브 에이전트의 도구 호출이 부모 도구 카드 안에 실시간 인라인 렌더링.
- **MCP Gateway** — [MCP](https://modelcontextprotocol.io/) 기반 중앙 집중식 도구 관리. MCP 서버 등록 → 자동 디스커버리 → 유저별 ACL이 적용된 카탈로그에서 에이전트에 바인딩.
- **LiteLLM Gateway** — [LiteLLM](https://github.com/BerriAI/litellm)이 모델 이름 접두사로 라우팅하고 Vault에서 유저별 Anthropic API 키를 주입.
- **멀티 백엔드 추론** — Claude API, Ollama, vLLM, AWS Bedrock; 설정으로 새 백엔드 추가.
- **계층화된 이그레스** — `charts/aviary-platform`의 baseline NetworkPolicy는 항상 적용; 환경별 Helm values의 `extraEgress`로 추가 규칙 union (K8s NP는 disjunction).
- **Redis 분리형 스트리밍** — supervisor가 런타임 SSE를 Redis로 publish; API 서버는 조립된 메시지 저장, WebSocket 클라이언트는 같은 Redis 스트림에서 독립적으로 replay.
- **실시간 설정 반영** — 에이전트 instruction · 도구 · MCP 바인딩이 매 메시지 턴마다 DB에서 갱신, Pod 재시작 불필요.
- **OIDC + ACL** — Keycloak/Okta 인증, 팀 동기화; 역할 계층 (`viewer` < `user` < `admin` < `owner`).
- **Vault 시크릿** — 유저별 API 키·도구 자격증명이 게이트웨이 수준에서 주입, Pod에 노출되지 않음.
- **로컬 K3s / 운영 EKS** — 동일 Helm 차트 사용. 로컬은 K3s 노드의 hostPath PVC, 운영은 values 하나만 바꿔 EFS RWX로 전환.

## 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| Web UI | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui |
| API 서버 | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| 에이전트 런타임 | Node.js, Python, claude-agent-sdk, Claude Code CLI |
| Agent Supervisor | Python, FastAPI, Redis, prometheus-client |
| LLM 게이트웨이 | [LiteLLM](https://github.com/BerriAI/litellm) |
| MCP Gateway | Python, FastAPI, [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) |
| 배포 | Helm 차트 (`charts/aviary-platform`, `charts/aviary-environment`) |
| 인프라 | PostgreSQL, Redis, Keycloak, Vault, Kubernetes (로컬: K3s, 운영: EKS) |

## 프로젝트 구조

```
aviary/
├── api/                  # API 서버 — 사용자 대면 REST + WebSocket + A2A
├── admin/                # Admin 콘솔 — 운영자 대면 웹 UI (설정 + endpoint 오버라이드)
├── web/                  # Web UI (Next.js)
├── runtime/              # 에이전트 런타임 — agent-agnostic 풀 멤버
├── shared/               # 공유 패키지 (OIDC, ACL, DB 모델)
├── mcp-gateway/          # MCP 도구 카탈로그, ACL, 프록시
├── agent-supervisor/     # Stateless SSE proxy + Redis publisher + /metrics
├── mcp-servers/          # 플랫폼 제공 MCP 서버 스텁
├── charts/
│   ├── aviary-platform/      # 네임스페이스, supervisor, baseline egress 등
│   └── aviary-environment/   # 런타임 환경 1개 (Deployment + Service + PVC + NP)
├── config/               # LiteLLM, Keycloak, K3s 설정
├── scripts/              # 개발 환경 설정 및 유틸리티
└── docker-compose.yml
```

## 시작하기

**사전 요구 사항:** Docker Desktop (또는 동등한 컨테이너 런타임)

```bash
git clone <repository-url>
cd aviary
./scripts/setup-dev.sh
```

이 명령 하나로 모든 이미지 빌드, 서비스 시작, DB 마이그레이션, Helm 차트(`aviary-platform` + 기본 `aviary-env-default`) 설치까지 완료됩니다.

| 서비스 | URL |
|--------|-----|
| Web UI | http://localhost:3000 |
| API 서버 | http://localhost:8000 |
| Admin 콘솔 | http://localhost:8001 |
| Supervisor Metrics | http://localhost:9000/metrics |
| Keycloak 관리자 | http://localhost:8080 |

테스트 계정: `user1@test.com` / `user2@test.com` (비밀번호: `password`)

```bash
docker compose up -d          # 시작
docker compose down           # 중지 (데이터 유지)
docker compose down -v        # 전체 초기화
```

소스 코드가 bind mount되어 `api/`, `admin/`, `web/` 수정이 핫 리로드로 반영됩니다.

### 커스텀 환경 추가

```bash
docker run --rm -v "$PWD/charts:/charts:ro" alpine/helm:3.14.4 template \
  aviary-env-gpu /charts/aviary-environment \
  --set name=gpu --set replicas=2 --set extraEgress='[...규칙...]' \
  | docker compose exec -T k8s kubectl apply -f -
```

Admin 콘솔 → 에이전트 상세에서 **Runtime Endpoint Override**에
`http://aviary-env-gpu.agents.svc:3000`을 저장. 다음 채팅 메시지부터 새 풀로 라우팅됩니다.

## 테스트

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
cd agent-supervisor && uv run pytest tests/ -v
```

## 주요 설계 결정

### Supervisor는 K8s 밖 + 엔드포인트 주입
Supervisor는 API/Admin과 동일한 배포 단위(dev: docker-compose)로 돌아가는 일반 서비스 — K8s 워크로드가 아닙니다. DB 연결도, K8s API 호출도 없고, 호출자(현재는 API 서버, 추후 Temporal worker / 배치 작업)가 `agent.runtime_endpoint`를 조회해 publish 요청 body로 전달. null이면 설정된 default(dev: `http://k8s:30300` — K3s NodePort; 운영: env Service DNS 또는 LB URL)로 fallback. K8s/GitOps 범위는 runtime pool에만 국한됩니다.

### Pod 라우팅 없는 Abort
kube-proxy는 연결 시점에 로드밸런싱하므로 supervisor → runtime TCP 연결은 수명 동안 하나의 pod에 pinned됩니다. Supervisor가 활성 publish task를 in-memory registry로 관리하고 abort는 `task.cancel()`로 처리: httpx 컨텍스트 종료 → TCP close → runtime pod의 close handler 발동 → SDK abort. 직접 pod 주소 지정도, runtime의 Redis 의존도, 특별한 K8s 위치 선정도 필요 없습니다.

### Helm으로 선언하는 환경
런타임 인프라는 전부 `charts/aviary-environment`에 있습니다. 새 환경을 띄우는 건 `helm template | kubectl apply`. 로컬과 운영의 차이는 values 파일 하나뿐(hostPath ↔ EFS, NodePort ↔ LoadBalancer). 애플리케이션 코드는 K8s를 직접 조작하지 않습니다.

### LiteLLM Gateway
에이전트 Pod가 LLM 백엔드를 직접 호출하지 않습니다. [LiteLLM](https://github.com/BerriAI/litellm)이 모델 이름 접두사로 백엔드(Claude API, Ollama, vLLM, Bedrock)를 선택하고 Vault에서 유저별 Anthropic API 키를 주입합니다. LiteLLM이 Anthropic Messages API를 네이티브로 지원하므로 claude-agent-sdk가 투명하게 동작합니다.

### MCP Gateway
에이전트 도구 호출은 중앙 집중식 [MCP](https://modelcontextprotocol.io/) Gateway를 통해 라우팅됩니다. 운영자가 Admin 콘솔로 백엔드 MCP 서버를 등록하면 도구가 자동 디스커버리되고, 사용자는 ACL이 적용된 카탈로그에서 에이전트에 바인딩합니다. 사용자의 OIDC 토큰이 엔드투엔드로 전파되고 외부 서비스로 전달되지 않습니다.

### 에이전트 간 호출 (A2A)
에이전트가 `@멘션`으로 다른 에이전트를 서브 에이전트로 호출. 런타임은 메시지마다 접근 가능한 에이전트별 도구가 등록된 HTTP MCP 서버를 구동. A2A 호출은 인증·ACL을 위해 API 서버를 경유. 서브 에이전트의 도구 호출은 부모 세션의 Redis 채널에 발행되어 프론트엔드에서 인라인 렌더링. 같은 세션의 모든 에이전트가 환경의 RWX PVC를 통해 `/workspace`를 공유합니다.

### 세션 격리
Claude CLI는 bubblewrap 마운트 네임스페이스에서 실행. 환경 PVC는 `/workspace-root/sessions/{sid}/shared/` (세션 공유 영역) + `/workspace-root/sessions/{sid}/agents/{aid}/{.claude,.venv}/` (agent·session별 오버레이)로 구성. bwrap이 이를 `/workspace`, `/workspace/.claude`, `/workspace/.venv`로 재매핑하므로 풀의 어느 pod에서든 샌드박스 뷰가 동일합니다.

### ACL 해석
권한은 6단계로 해석됩니다: 에이전트 소유자 → 직접 사용자 ACL → 팀 ACL → 공개 가시성 → 팀 가시성 → 거부. 역할: `viewer` < `user` < `admin` < `owner`.
