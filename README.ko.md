# Aviary

**멀티테넌트 AI 에이전트 플랫폼**

[English](./README.md)

Aviary는 웹 UI를 통해 AI 에이전트를 생성, 설정, 배포, 사용할 수 있는 엔터프라이즈 플랫폼입니다. 각 에이전트는 격리된 Kubernetes 네임스페이스에서 장기 실행 Pod으로 구동되며, 여러 세션이 동일 Pod을 공유하면서 bubblewrap 샌드박싱으로 커널 수준의 격리를 제공합니다.

## 아키텍처

```
┌────────────────────────────────────────────────────────────────┐
│                        Web UI (Next.js 15)                     │
│      에이전트 카탈로그 · 생성/편집 · 채팅 세션 · ACL 설정       │
└───────────────┬────────────────────────────────────────────────┘
                │ REST + WebSocket
┌───────────────▼────────────────────────────────────────────────┐
│                      API 서버 (FastAPI)                         │
│    OIDC 인증 · Agent CRUD · 세션 관리 · ACL · Vault 클라이언트   │
└───┬───────────┬───────────┬────────────────────────────────────┘
    │           │           │
    │           │   ┌───────▼────────────────────────────────────┐
    │           │   │             플랫폼 서비스                    │
    │           │   │                                            │
    │           │   │  ┌─────────────────┐  ┌──────────────────┐ │
    │           │   │  │ Inference Router │  │ Credential Proxy │ │
    │           │   │  │ (LLM 게이트웨이) │  │ (Vault 시크릿)   │ │
    │           │   │  └────────┬────────┘  └──────────────────┘ │
    │           │   │           │                                 │
    │           │   │     ┌─────┴───────────────────┐            │
    │           │   │     ▼            ▼            ▼            │
    │           │   │  Claude API   Ollama/vLLM   Bedrock        │
    │           │   └────────────────────────────────────────────┘
    │           │
    │           │ K8s API
    │   ┌───────▼────────────────────────────────────────────────┐
    │   │                  Kubernetes 클러스터                      │
    │   │                                                        │
    │   │  ┌─── NS: platform ──────────────────────────────────┐ │
    │   │  │  ┌─────────────────┐                               │ │
    │   │  │  │  Egress Proxy   │  Pod IP → 에이전트 식별         │ │
    │   │  │  │  (포워드 프록시  │  + 에이전트별 정책 적용         │ │
    │   │  │  │   + 허용 목록)   │                               │ │
    │   │  │  └────────┬────────┘                               │ │
    │   │  │           │                                        │ │
    │   │  │           ▼                                        │ │
    │   │  │     외부 API (GitHub, S3, ...)                      │ │
    │   │  └────────────────────────────────────────────────────┘ │
    │   │                                                        │
    │   │  ┌─── NS: agent-{id} ──────┐  ┌── NS: agent-{id} ──┐ │
    │   │  │  Agent Pod (1-N)         │  │  Agent Pod (1-N)    │ │
    │   │  │  claude-agent-sdk        │  │  claude-agent-sdk   │ │
    │   │  │  + Claude Code CLI       │  │  + Claude Code CLI  │ │
    │   │  │  + bwrap 샌드박스         │  │  + bwrap 샌드박스    │ │
    │   │  │  PVC: /workspace         │  │  PVC: /workspace    │ │
    │   │  │                          │  │                     │ │
    │   │  │  LLM ──▶ Inference Router│  │                     │ │
    │   │  │  시크릿 ▶ Cred. Proxy    │  │  NetworkPolicy:     │ │
    │   │  │  HTTP ──▶ Egress Proxy   │  │    deny-by-default  │ │
    │   │  └──────────────────────────┘  └─────────────────────┘ │
    │   └────────────────────────────────────────────────────────┘
    │
    │  ┌───────────────┐  ┌──────────────┐  ┌────────────────┐
    └─▶│  PostgreSQL    │  │    Redis      │  │   Keycloak     │
       │  DB, 세션,     │  │  pub/sub,     │  │   OIDC 인증,   │
       │  ACL, 에이전트  │  │  egress 규칙  │  │   팀 동기화     │
       └───────────────┘  └──────────────┘  └────────────────┘
```

**플랫폼 서비스** (Inference Router, Credential Proxy)는 상태 없는 HTTP 프록시로 K8s 외부에서 실행됩니다. API 서버와 에이전트 Pod 모두 직접 접근합니다. **Egress Proxy**는 Pod IP로 에이전트를 식별하고 NetworkPolicy로 deny-by-default를 강제하므로 K8s 안에서 실행됩니다.

## 주요 기능

- **에이전트별 Pod (멀티 세션)** — 각 에이전트가 장기 실행 Deployment(1-N 레플리카)로 여러 세션을 동시 처리, 세션 부하 기반 자동 스케일링
- **bubblewrap 세션 격리** — 각 세션이 bwrap 마운트 네임스페이스 내에서 실행되어 다른 세션의 파일이 커널 수준에서 비가시
- **에이전트별 네임스페이스** — NetworkPolicy, ResourceQuota, ServiceAccount가 에이전트 단위로 격리
- **Egress Proxy** — 에이전트 Pod의 모든 아웃바운드 HTTP/HTTPS가 중앙 프록시를 통해 라우팅되며, 에이전트별 허용 목록(CIDR, 정확한 도메인, 와일드카드 `*.example.com`)으로 제어; 기본값은 모두 차단, 정책 변경 시 Pod 재시작 없이 즉시 적용
- **claude-agent-sdk 기반** — `ClaudeSDKClient`를 통한 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 하네스의 전체 기능: 도구, 서브 에이전트, MCP 서버, 파일 I/O, 셸 실행
- **Inference Router** — 중앙 집중식 LLM 게이트웨이; 모델명으로 백엔드가 투명하게 라우팅
- **멀티 백엔드 추론** — Claude API, Ollama, vLLM, AWS Bedrock; 새 백엔드 추가 시 NetworkPolicy 변경 불필요
- **실시간 설정 반영** — 에이전트 설정(instruction, tools)이 매 메시지마다 DB에서 전달되어 Pod 재시작 없이 즉시 적용
- **OIDC 인증 + 팀 동기화** — Keycloak (개발) / Okta (운영); IdP 그룹이 로그인 시 팀으로 자동 동기화
- **세분화된 ACL** — 7단계 권한 해석, 역할 계층 (`viewer` < `user` < `admin` < `owner`)
- **자격증명 프록시** — 시크릿이 세션 Pod에 노출되지 않고, 공유 프록시가 Vault에서 주입
- **실시간 채팅** — WebSocket 스트리밍, Redis pub/sub 기반 다중 사용자 공유 세션

## 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| Web UI | Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui |
| API 서버 | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| 에이전트 런타임 | Python 3.12, claude-agent-sdk, Claude Code CLI, Node.js 22 |
| Inference Router | Python 3.12, FastAPI — Anthropic Messages API 프록시 |
| Egress Proxy | Python 3.12, asyncio — HTTP/HTTPS 포워드 프록시 + 정책 적용 |
| 데이터베이스 | PostgreSQL 16 |
| 캐시 / PubSub | Redis 7 |
| 인증 | Keycloak 25 (개발) / Okta (운영) — OIDC |
| 시크릿 관리 | HashiCorp Vault |
| 오케스트레이션 | Kubernetes (로컬: K3s) |
| 추론 백엔드 | Claude API, Ollama, vLLM, AWS Bedrock |

## 프로젝트 구조

```
aviary/
├── api/                     # API 서버 (FastAPI)
│   ├── app/
│   │   ├── auth/            # OIDC 검증, 팀 동기화
│   │   ├── db/              # SQLAlchemy 모델, Alembic 마이그레이션
│   │   ├── routers/         # REST + WebSocket 엔드포인트
│   │   ├── services/        # 비즈니스 로직 (agent, session, k8s, vault, acl, redis)
│   │   └── schemas/         # Pydantic 모델
│   └── tests/               # pytest (16개)
├── web/                     # Web UI (Next.js 15)
│   └── src/
│       ├── app/             # 페이지 (agents, sessions, login)
│       ├── components/      # 채팅, 에이전트 관리, UI 기본 요소
│       └── lib/             # API 클라이언트, 인증, WebSocket
├── runtime/                 # 에이전트 런타임 (에이전트 Pod 내부에서 실행)
│   └── app/                 # claude-agent-sdk 하네스, 세션 매니저
├── inference-router/        # LLM 게이트웨이
│   └── app/                 # Anthropic API 프록시, 백엔드 라우팅
├── credential-proxy/        # 시크릿 주입 프록시
│   └── app/                 # Vault 클라이언트, 세션 리졸버
├── egress-proxy/            # HTTP/HTTPS 이그레스 프록시
│   └── app/                 # 포워드 프록시, 에이전트별 정책 체커
├── config/                  # Keycloak realm, K3s 설정
├── k8s/platform/            # K8s 매니페스트
├── scripts/                 # 개발 환경 설정, DB 초기화, 시딩
└── docker-compose.yml       # 전체 개발 환경
```

## 시작하기

### 사전 요구 사항

- Docker Desktop (또는 동등한 컨테이너 런타임)

### 빠른 시작

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
| Inference Router | http://localhost:8090 |
| Credential Proxy | http://localhost:8091 |
| Keycloak 관리자 | http://localhost:8080 (admin/admin) |
| Vault | http://localhost:8200 |

### 테스트 계정

| 이메일 | 비밀번호 | 역할 | 팀 |
|--------|----------|------|----|
| admin@test.com | password | 플랫폼 관리자 | engineering |
| user1@test.com | password | 일반 사용자 | engineering, product |
| user2@test.com | password | 일반 사용자 | data-science |

### 주요 명령어

```bash
docker compose up -d          # 시작
docker compose down           # 중지 (데이터 유지)
docker compose down -v        # 중지 + 모든 데이터 삭제
docker compose logs -f api    # 로그 확인
```

### 개발

소스 코드가 컨테이너에 bind mount되어 있어서 `api/`, `web/`, `inference-router/`, `credential-proxy/` 파일 수정이 핫 리로드로 자동 반영됩니다.

```bash
# 의존성 변경 시 리빌드
docker compose up -d --build api
docker compose up -d --build web

# K8s 이미지 리빌드 (runtime, egress-proxy)
docker build -t aviary-runtime:latest ./runtime/
docker build -t aviary-egress-proxy:latest ./egress-proxy/
docker save aviary-runtime:latest aviary-egress-proxy:latest | docker compose exec -T k8s ctr images import -
```

## 테스트

```bash
docker compose exec api pytest tests/ -v
```

16개 테스트: 헬스, 에이전트 CRUD, ACL (가시성, 권한 부여/거부), 세션 (생성, 목록, 접근 제어, 아카이브). 전용 `aviary_test` 데이터베이스와 토큰 기반 mock 인증으로 다중 사용자 시나리오를 지원합니다.

## API 엔드포인트

### 인증
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/auth/config` | OIDC 프로바이더 설정 |
| POST | `/api/auth/callback` | 인증 코드를 토큰으로 교환 |
| GET | `/api/auth/me` | 현재 사용자 정보 |

### 에이전트
| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/agents` | 에이전트 목록 (ACL 기반 필터링) |
| POST | `/api/agents` | 에이전트 생성 + K8s 네임스페이스 프로비저닝 |
| GET/PUT/DELETE | `/api/agents/{id}` | 조회 / 수정 / 소프트 삭제 |

### 세션 및 채팅
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/agents/{id}/sessions` | 세션 생성 (private 또는 team) |
| GET | `/api/sessions/{id}` | 세션 상세 + 메시지 히스토리 |
| WS | `/api/sessions/{id}/ws` | 실시간 채팅 |
| POST | `/api/sessions/{id}/invite` | 이메일로 사용자 초대 |

### ACL, 자격증명, 카탈로그
| 메서드 | 경로 | 설명 |
|--------|------|------|
| CRUD | `/api/agents/{id}/acl` | 접근 권한 관리 |
| CRUD | `/api/agents/{id}/credentials` | 시크릿 관리 (Vault 연동) |
| GET | `/api/catalog`, `/api/catalog/search` | 에이전트 탐색 / 검색 |
| GET | `/api/inference/backends`, `/{backend}/models` | 추론 백엔드 정보 |

## 주요 설계 결정

### Inference Router
세션 Pod는 LLM 백엔드를 직접 호출하지 않습니다. 모든 추론은 중앙 라우터를 통하며, 모델명으로 백엔드를 결정합니다 (예: `claude-*` → Claude API, `qwen:*` → Ollama). API 자격증명을 중앙 관리하고, Anthropic Messages API를 네이티브로 사용하기 때문에 claude-agent-sdk의 모든 기능이 보존됩니다. API 서버도 모델 목록 조회 시 동일 라우터를 경유하여, 접근 제어의 단일 적용 지점을 보장합니다.

### Egress Proxy
에이전트 Pod의 모든 아웃바운드 HTTP/HTTPS 트래픽은 중앙 포워드 프록시를 통해 라우팅됩니다 (`HTTP_PROXY`/`HTTPS_PROXY` 환경변수). 프록시는 소스 Pod IP를 K8s 네임스페이스로 변환하여 에이전트를 식별하고, Redis에 저장된 에이전트별 정책을 적용합니다. 지원하는 규칙: CIDR 범위, 정확한 도메인, 와일드카드 도메인(`*.example.com`), 전체 허용. 기본값은 모두 차단이며, 정책 변경 시 Redis 캐시 무효화로 Pod 재시작 없이 즉시 적용됩니다.

### 실시간 Agent 설정 반영
에이전트 설정(instruction, tools, policy)은 매 메시지 턴마다 DB에서 런타임으로 전달됩니다. 편집 내용이 Pod 재시작 없이 다음 메시지부터 즉시 적용되며, 다른 사용자의 세션에 영향을 주지 않습니다.

### ACL 해석
권한은 7단계로 해석됩니다: 플랫폼 관리자 → 에이전트 소유자 → 직접 사용자 ACL → 팀 ACL → 공개 가시성 → 팀 가시성 → 거부. 역할 계층: `viewer` < `user` < `admin` < `owner`.

### 에이전트 Pod 전략
각 에이전트는 장기 실행 Deployment로 구동되며, 스폰 전략을 설정할 수 있습니다: `lazy` (기본값, 첫 메시지 시 생성), `eager` (에이전트 생성 시), `manual` (관리자가 활성화). 여러 세션이 동일 Pod을 공유하며 워크스페이스 디렉토리와 bubblewrap 샌드박스로 격리됩니다. 유휴 에이전트(7일)는 삭제되지 않고 0으로 스케일 다운되며, 다음 메시지에서 재활성화됩니다.

### 세션 격리 (bubblewrap)
PATH의 `claude` CLI 바이너리는 실제 바이너리를 bubblewrap 마운트 네임스페이스 내에서 실행하는 래퍼 스크립트입니다. 각 세션은 자신의 워크스페이스 디렉토리(`/workspace/sessions/{session_id}/`)만 볼 수 있으며, 다른 세션의 파일은 마운트 네임스페이스에 존재하지 않습니다. CLI 세션 데이터는 PVC에 저장되어 Pod 재시작 후에도 대화를 재개할 수 있습니다.

## 서비스

| 서비스 | 포트 | 역할 |
|--------|------|------|
| `api` | 8000 | API 서버 |
| `web` | 3000 | Web UI |
| `inference-router` | 8090 | LLM 게이트웨이 |
| `credential-proxy` | 8091 | 시크릿 주입 프록시 |
| `postgres` | 5432 | 데이터베이스 |
| `redis` | 6379 | 캐시, pub/sub, 프레즌스 |
| `keycloak` | 8080 | OIDC 프로바이더 |
| `vault` | 8200 | 시크릿 관리 |
| `k8s` | 6443 | Kubernetes 클러스터 |

## 라이선스

Private — 내부 전용.
