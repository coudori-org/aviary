# AgentBox

**멀티테넌트 AI 에이전트 플랫폼**

[English](./README.md)

AgentBox는 내부 직원이 웹 UI를 통해 AI 에이전트를 생성, 설정, 배포, 사용할 수 있는 엔터프라이즈 플랫폼입니다. 각 에이전트는 격리된 Kubernetes 네임스페이스에서 실행되며, 각 사용자 세션은 전용 Pod에서 구동되어 커널 수준의 격리를 제공합니다.

## 아키텍처

```
┌───────────────────────────────────────────────────────────────┐
│                       Web UI (Next.js 15)                      │
│     에이전트 카탈로그 · 생성/편집 · 채팅 세션 · ACL 설정        │
└──────────────┬────────────────────────────────────────────────┘
               │ REST + WebSocket
┌──────────────▼────────────────────────────────────────────────┐
│                    API 서버 (FastAPI)                           │
│   OIDC 인증 · Agent CRUD · 세션 관리 · ACL · Vault 클라이언트   │
└──────────────┬────────────────────────────────────────────────┘
               │ K8s API Proxy
┌──────────────▼────────────────────────────────────────────────┐
│                    Kubernetes 클러스터                           │
│                                                                │
│  NS: platform                                                  │
│  ┌──────────────────┐ ┌────────────────┐ ┌──────────────────┐ │
│  │ Inference Router  │ │ Credential     │ │ Image Warmer     │ │
│  │ (LLM 게이트웨이)  │ │ Proxy (Vault)  │ │ (DaemonSet)      │ │
│  └────────┬─────────┘ └────────────────┘ └──────────────────┘ │
│           │                                                    │
│     ┌─────┴──────────────────────┐                             │
│     ▼              ▼             ▼                             │
│  Claude API    Ollama/vLLM    Bedrock                          │
│                                                                │
│  NS: agent-{id}           NS: agent-{id}                      │
│  ┌─────────────────┐     ┌─────────────────┐                  │
│  │ 세션 Pod          │     │ 세션 Pod          │                  │
│  │ claude-agent-sdk │     │ claude-agent-sdk │                  │
│  │ + Claude Code CLI│     │ + Claude Code CLI│                  │
│  │ PVC: /workspace  │     │ PVC: /workspace  │                  │
│  └─────────────────┘     └─────────────────┘                  │
└───────────────────────────────────────────────────────────────┘
```

## 주요 기능

- **세션별 Pod 격리** — 각 채팅 세션이 전용 K8s Pod에서 실행되며 영속 워크스페이스(PVC) 보유
- **에이전트별 네임스페이스** — NetworkPolicy, ResourceQuota, ServiceAccount가 에이전트 단위로 격리
- **claude-agent-sdk 기반** — [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 하네스의 전체 기능: 도구, 서브 에이전트, MCP 서버, 파일 I/O, 셸 실행
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
| 데이터베이스 | PostgreSQL 16 |
| 캐시 / PubSub | Redis 7 |
| 인증 | Keycloak 25 (개발) / Okta (운영) — OIDC |
| 시크릿 관리 | HashiCorp Vault |
| 오케스트레이션 | Kubernetes (로컬: K3s) |
| 추론 백엔드 | Claude API, Ollama, vLLM, AWS Bedrock |

## 프로젝트 구조

```
agentbox/
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
├── runtime/                 # 에이전트 런타임 (세션 Pod 내부에서 실행)
│   └── app/                 # claude-agent-sdk 하네스, 히스토리
├── inference-router/        # LLM 게이트웨이 (platform 네임스페이스)
│   └── app/                 # Anthropic API 프록시, 백엔드 라우팅
├── credential-proxy/        # 시크릿 주입 프록시 (platform 네임스페이스)
│   └── app/                 # Vault 클라이언트, 세션 리졸버
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
cd agentbox
./scripts/setup-dev.sh
```

이 명령 하나로 모든 이미지 빌드, 서비스 시작 (API, Web, PostgreSQL, Redis, Keycloak, Vault, K3s), DB 마이그레이션, 런타임 이미지 K3s 로드까지 완료됩니다.

| 서비스 | URL |
|--------|-----|
| Web UI | http://localhost:3000 |
| API 서버 | http://localhost:8000 |
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

소스 코드가 컨테이너에 bind mount되어 있어서 `api/`, `web/` 파일 수정이 자동 반영됩니다 (uvicorn `--reload`, Next.js HMR).

```bash
# 의존성 변경 시 리빌드
docker compose up -d --build api
docker compose up -d --build web

# 런타임 이미지 리빌드 (K3s 내부에서 실행)
docker build -t agentbox-runtime:latest ./runtime/
docker save agentbox-runtime:latest | docker compose exec -T k3s ctr images import -
```

## 테스트

```bash
docker compose exec api pytest tests/ -v
```

16개 테스트: 헬스, 에이전트 CRUD, ACL (가시성, 권한 부여/거부), 세션 (생성, 목록, 접근 제어, 아카이브). 전용 `agentbox_test` 데이터베이스와 토큰 기반 mock 인증으로 다중 사용자 시나리오를 지원합니다.

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
세션 Pod는 LLM 백엔드를 직접 호출하지 않습니다. 모든 추론은 platform 네임스페이스의 중앙 라우터를 통하며, 모델명으로 백엔드를 결정합니다 (예: `claude-*` → Claude API, `qwen:*` → Ollama). NetworkPolicy를 단순하게 유지하고, API 자격증명을 중앙 관리하며, Anthropic Messages API를 그대로 사용하기 때문에 claude-agent-sdk의 모든 기능이 보존됩니다.

### 실시간 Agent 설정 반영
에이전트 설정(instruction, tools, policy)은 매 메시지 턴마다 DB에서 런타임으로 전달됩니다. 편집 내용이 Pod 재시작 없이 다음 메시지부터 즉시 적용되며, 다른 사용자의 세션에 영향을 주지 않습니다.

### ACL 해석
권한은 7단계로 해석됩니다: 플랫폼 관리자 → 에이전트 소유자 → 직접 사용자 ACL → 팀 ACL → 공개 가시성 → 팀 가시성 → 거부. 역할 계층: `viewer` < `user` < `admin` < `owner`.

### 세션 Pod 생명주기
Pod는 첫 메시지 시 생성되며 기존 PVC를 재사용하여 워크스페이스를 보존합니다. 재시작 시 stale Pod 참조를 자동 감지하고 정리하여, 외부 개입 없이 자가 복구합니다.

## Docker Compose 서비스

| 서비스 | 포트 | 역할 |
|--------|------|------|
| `api` | 8000 | API 서버 |
| `web` | 3000 | Web UI |
| `postgres` | 5432 | 데이터베이스 |
| `redis` | 6379 | 캐시, pub/sub, 프레즌스 |
| `keycloak` | 8080 | OIDC 프로바이더 |
| `vault` | 8200 | 시크릿 관리 |
| `k3s` | 6443 | Kubernetes 클러스터 |

## 라이선스

Private — 내부 전용.
