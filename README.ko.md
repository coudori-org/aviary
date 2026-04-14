# Aviary

**멀티테넌트 AI 에이전트 플랫폼**

[English](./README.md)

Aviary는 웹 UI를 통해 AI 에이전트를 생성, 설정, 사용할 수 있는 엔터프라이즈 플랫폼입니다. 각 에이전트는 공용 `agents` 네임스페이스의 장기 실행 Deployment로 구동되며, 여러 세션이 동일 Pod을 공유하면서 bubblewrap 샌드박싱(커널 수준 격리) + baseline/per-agent NetworkPolicy(네트워크 수준 격리)로 분리됩니다.

## 아키텍처

```
┌────────────────────────────────────────────────────────────────┐
│                        Web UI (Next.js)                        │
│      에이전트 카탈로그 · 생성/편집 · 채팅 세션 · ACL 설정       │
└───────────────┬────────────────────────────────────────────────┘
                │ REST + WebSocket
┌───────────────▼────────────────────────────────────────────────┐
│                      API 서버 (FastAPI)                         │
│       OIDC 인증 · Agent CRUD · 세션 관리 · ACL · A2A            │
└───┬───────────┬───────────┬────────────────────────────────────┘
    │           │           │
    │           │           │           ┌────────────────────────┐
    │           │           │           │  Admin 콘솔            │
    │           │           │           │  정책 · 스케일링 ·      │
    │           │           │           │  배포 관리 · Web UI     │
    │           │           │           └───────────┬────────────┘
    │           │           │                       │
    │           │   ┌───────▼────────────────────────────────────┐
    │           │   │             플랫폼 서비스                    │
    │           │   │                                            │
    │           │   │  ┌─────────────────┐                       │
    │           │   │  │ LiteLLM Gateway │◀── Vault              │
    │           │   │  │ (모델 라우팅,    │    (유저별 API 키)    │
    │           │   │  │  API 키 주입)    │                       │
    │           │   │  └────────┬────────┘                       │
    │           │   │  ┌────────▼────────┐                       │
    │           │   │  │ Portkey Gateway │                       │
    │           │   │  │ (가드레일,       │                       │
    │           │   │  │  트레이싱, 캐싱) │                       │
    │           │   │  └────────┬────────┘                       │
    │           │   │     ┌─────┴───────────────────┐            │
    │           │   │     ▼            ▼            ▼            │
    │           │   │  Claude API   Ollama/vLLM   Bedrock        │
    │           │   │                                            │
    │           │   │  ┌─────────────────────────────────────┐   │
    │           │   │  │ MCP Gateway                         │◀─ Vault
    │           │   │  │ (도구 카탈로그, ACL, 프록시,          │   (도구 자격증명)
    │           │   │  │  OIDC 인증, 자동 디스커버리)          │   │
    │           │   │  └────────┬────────────────────────────┘   │
    │           │   │           ▼                                 │
    │           │   │     백엔드 MCP 서버                          │
    │           │   └────────────────────────────────────────────┘
    │           │
    │   ┌───────▼────────────────────────────────────────────────┐
    │   │                  Kubernetes 클러스터                      │
    │   │                                                        │
    │   │  ┌─── NS: platform ──────────────────────────────────┐ │
    │   │  │  ┌────────────────────────────────────────────┐    │ │
    │   │  │  │ Agent Supervisor                           │    │ │
    │   │  │  │ (0→1 activator + SSE→Redis publisher,      │    │ │
    │   │  │  │  NetworkPolicy / ScaledObject 관리)         │    │ │
    │   │  │  └────────────────────────────────────────────┘    │ │
    │   │  │   KEDA (0↔N 스케일링) · kube-router (NP 강제)       │ │
    │   │  └────────────────────────────────────────────────────┘ │
    │   │                                                        │
    │   │  ┌─── NS: agents ───────────────────────────────────┐  │
    │   │  │  baseline NetworkPolicy                          │  │
    │   │  │    (DNS + platform + LiteLLM + MCP GW + API)     │  │
    │   │  │                                                  │  │
    │   │  │  Agent Deployment × N  (에이전트당 하나)          │  │
    │   │  │  claude-agent-sdk + Claude Code CLI + Python     │  │
    │   │  │  bwrap 샌드박스 · 공유 홈 · per-agent .claude    │  │
    │   │  │                                                  │  │
    │   │  │  LLM ──▶ LiteLLM                                 │  │
    │   │  │  도구 ──▶ MCP GW                                  │  │
    │   │  │  외부 API ▶ ServiceAccount에 SG가 붙은 경우만     │  │
    │   │  └──────────────────────────────────────────────────┘  │
    │   └────────────────────────────────────────────────────────┘
    │
    └─▶ PostgreSQL · Redis · Keycloak · Vault
```

## 주요 기능

- **에이전트별 Deployment (멀티 세션)** — 각 에이전트가 KEDA로 0↔N 스케일되는 Deployment; 여러 세션이 동일 Pod을 공유하고 bwrap 워크디렉토리로 세션 분리
- **런타임 백엔드 추상화** — `RuntimeBackend` 프로토콜(K3S 구현, EKS Native / EKS Fargate 스텁)로 워크스페이스 · 아이덴티티 · 라이프사이클을 일관된 인터페이스로 관리
- **bubblewrap 세션 격리** — 각 세션이 커널 수준 마운트 네임스페이스에서 실행; 같은 세션의 에이전트들은 워크스페이스 디렉토리를 공유하여 파일 교환이 가능하고, `.claude/` 컨텍스트만 PVC 오버레이로 에이전트별 분리
- **에이전트 간 호출 (A2A)** — instruction이나 채팅에서 `@멘션`으로 서브 에이전트 호출; 서브 에이전트의 도구 호출이 부모 도구 카드 안에 실시간 인라인 렌더링
- **MCP Gateway** — [MCP](https://modelcontextprotocol.io/) 기반 중앙 집중식 도구 관리; MCP 서버 등록 → 자동 디스커버리 → 유저별 ACL이 적용된 카탈로그에서 에이전트에 바인딩
- **LiteLLM + Portkey Gateway** — 2계층 LLM 게이트웨이: [LiteLLM](https://github.com/BerriAI/litellm)이 모델 라우팅과 유저별 API 키 주입, [Portkey](https://github.com/portkey-ai/gateway)가 가드레일, 트레이싱, 캐싱
- **멀티 백엔드 추론** — Claude API, Ollama, vLLM, AWS Bedrock; 설정으로 새 백엔드 추가
- **AWS 스타일 이그레스** — 네임스페이스 baseline NetworkPolicy + 선택적 ServiceAccount 바인딩(추가 SG 프로파일); AWS SG처럼 규칙이 union으로 적용
- **KEDA 기반 스케일링** — PostgreSQL scaler가 에이전트별 활성 세션 수를 카운트; supervisor는 cold-start 0→1만 동기 처리하고 KEDA가 1↔N↔0 담당
- **Redis 분리형 스트리밍** — supervisor가 런타임 SSE를 소비해 Redis로 publish; API 서버와 WebSocket 클라이언트는 독립적으로 subscribe
- **실시간 설정 반영** — 에이전트 instruction과 도구가 매 메시지 턴마다 DB에서 갱신, Pod 재시작 불필요
- **OIDC + ACL** — Keycloak/Okta 인증, 팀 동기화; 역할 계층 (`viewer` < `user` < `admin` < `owner`)
- **Vault 시크릿** — 유저별 API 키와 도구 자격증명이 게이트웨이 수준에서 주입, Pod에 노출되지 않음

## 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| Web UI | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui |
| API 서버 | Python, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| 에이전트 런타임 | Node.js, Python, claude-agent-sdk, Claude Code CLI |
| LLM 게이트웨이 | [LiteLLM](https://github.com/BerriAI/litellm) + [Portkey](https://github.com/portkey-ai/gateway) |
| MCP Gateway | Python, FastAPI, [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) |
| 인프라 | PostgreSQL, Redis, Keycloak, Vault, Kubernetes (로컬: K3s) |

## 프로젝트 구조

```
aviary/
├── api/                  # API 서버 — 사용자 대면 REST + WebSocket + A2A
├── admin/                # Admin 콘솔 — 운영자 대면 웹 UI
├── web/                  # Web UI (Next.js)
├── runtime/              # 에이전트 런타임 (K8s 에이전트 Pod 내부)
├── shared/               # 공유 패키지 (OIDC, ACL, DB 모델)
├── mcp-gateway/          # MCP 도구 카탈로그, ACL, 프록시
├── agent-supervisor/     # K8s 라이프사이클 매니저 (K8s 내부)
├── mcp-servers/          # 플랫폼 제공 MCP 서버 스텁
├── k8s/                  # K8s 매니페스트
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

이 명령 하나로 모든 이미지 빌드, 서비스 시작, DB 마이그레이션, K8s 클러스터 프로비저닝까지 완료됩니다.

| 서비스 | URL |
|--------|-----|
| Web UI | http://localhost:3000 |
| API 서버 | http://localhost:8000 |
| Admin 콘솔 | http://localhost:8001 |
| Keycloak 관리자 | http://localhost:8080 |

테스트 계정: `user1@test.com` / `user2@test.com` (비밀번호: `password`)

```bash
docker compose up -d          # 시작
docker compose down           # 중지 (데이터 유지)
docker compose down -v        # 전체 초기화
```

소스 코드가 bind mount되어 `api/`, `web/` 수정이 핫 리로드로 자동 반영됩니다.

## 테스트

```bash
docker compose exec api pytest tests/ -v
docker compose exec admin pytest tests/ -v
```

## 주요 설계 결정

### LiteLLM + Portkey Gateway
에이전트 Pod는 LLM 백엔드를 직접 호출하지 않습니다. [LiteLLM](https://github.com/BerriAI/litellm)이 모델 이름 접두사로 백엔드를 결정하고, [Portkey AI Gateway](https://github.com/portkey-ai/gateway)가 가드레일, 트레이싱, 로깅, 캐싱을 제공합니다. LiteLLM이 Anthropic Messages API를 네이티브로 지원하므로 claude-agent-sdk가 투명하게 동작합니다. API 자격증명, 속도 제한, 관측성이 중앙 집중화됩니다.

### MCP Gateway
에이전트 도구 호출은 중앙 집중식 [MCP](https://modelcontextprotocol.io/) Gateway를 통해 라우팅됩니다. 운영자가 Admin 콘솔을 통해 백엔드 MCP 서버를 등록하면 도구가 자동 디스커버리됩니다. 사용자는 ACL이 적용된 카탈로그에서 도구를 선택하여 에이전트에 바인딩합니다. 사용자의 OIDC 토큰이 권한 검증을 위해 엔드투엔드로 전파되며, 외부 서비스로 전달되지 않습니다.

### 에이전트 간 호출 (A2A)
에이전트가 `@멘션`으로 다른 에이전트를 서브 에이전트로 호출할 수 있습니다. 런타임은 메시지마다 접근 가능한 에이전트별 도구가 등록된 HTTP MCP 서버를 구동합니다. A2A 호출은 인증과 ACL을 위해 API 서버를 통해 라우팅됩니다. 서브 에이전트의 도구 호출은 부모 세션의 Redis 채널에 발행되어 프론트엔드에서 인라인 렌더링됩니다. 같은 세션의 모든 에이전트는 hostPath 볼륨으로 동일한 워크스페이스를 공유합니다.

### 세션 격리
Claude CLI는 bubblewrap 마운트 네임스페이스 내에서 실행됩니다. 같은 세션의 모든 에이전트가 `/workspace`를 hostPath로 공유하여 파일 교환이 자유롭습니다. 각 에이전트의 `.claude/`는 PVC 오버레이로 격리되어 대화 히스토리가 독립적으로 유지됩니다. 다른 세션의 파일은 마운트 네임스페이스 수준에서 보이지 않습니다.

### ACL 해석
권한은 6단계로 해석됩니다: 에이전트 소유자 → 직접 사용자 ACL → 팀 ACL → 공개 가시성 → 팀 가시성 → 거부. 역할: `viewer` < `user` < `admin` < `owner`.
