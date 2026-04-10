# UX/UI Backlog

웹 풀 리뉴얼 (commit `e4c83f0`) 이후 제안된 UX 개선 아이템 목록.
디자인 시스템과 코드 구조는 바뀌었지만 인터랙션은 그대로 — 이 백로그는
"느낌"을 넘어 사용자 경험을 실제로 변화시키기 위한 작업 단위 모음이다.

## 워크플로 (사용자가 정의한 진행 방식)

이 백로그는 **한 번에 다 구현하지 않는다**. 사용자가 명시적으로 진행을
지시할 때만, 한 아이템씩 다음 절차로 처리한다.

1. **사용자 트리거**: 사용자가 "다음 거", "진행하자", "UX-XXX 진행" 등으로 시작 지시
2. **아이템 제시**: 가장 먼저 `pending` 상태인 아이템(또는 사용자가 지정한 ID)을
   골라 제목·설명·접근 방법을 다시 보여준다. 곧바로 코드를 건드리지 않는다.
3. **사용자 결정**: 사용자가 다음 중 하나를 선택
   - **진행** → 4단계로
   - **스킵** → 다음 pending 아이템으로 (현재 아이템은 그대로 pending 유지)
   - **리젝트** → 상태를 `rejected`로 바꾸고 사유 기록, 다음 아이템으로
4. **구현**: 아이템 상태를 `in-progress`로 표시하고 코드 변경. 끝나면 `testing`으로.
5. **사용자 테스트**: 사용자가 직접 띄우고 동작 확인.
6. **사용자 판정**:
   - **채택** → 상태 `accepted`로 변경, 커밋, 다음 아이템으로
   - **롤백** → 변경사항 revert, 상태를 `rejected` 또는 `rework-needed`로
     (사유 기록), 다음 아이템으로
   - **수정 요청** → 추가 작업 후 다시 5단계로

**중요한 규칙**:
- 한 번에 한 아이템만 in-progress 상태가 될 수 있다.
- 아이템을 임의로 재배열하지 않는다 (사용자가 지정 안 하면 ID 순서대로).
- accepted된 아이템은 별도 commit으로 분리한다 (한 아이템 = 한 commit).
- 진행 중에 새 아이디어가 떠오르면 별도 아이템으로 백로그 끝에 추가한다.

## 상태 표기

| 상태 | 의미 |
|---|---|
| `pending` | 아직 검토되지 않음 |
| `in-progress` | 현재 구현 중 (한 번에 한 개만) |
| `testing` | 구현 완료, 사용자 테스트 대기 |
| `accepted` | 사용자가 채택, 커밋 완료 |
| `rejected` | 사용자가 거절 (필요시 사유 기록) |
| `rework-needed` | 수정 필요 (사유 기록) |

## 우선순위 마커

- ⭐ = 가성비 좋음 (구현 비용 낮음)
- 🔥 = 임팩트 큼 (사용자 체감 효과 큼)

## TOP 5 추천 (가성비 × 임팩트)

작업 순서를 고민할 때 이 5개부터 시작 권장:

1. **ENTRY-1** 카드에서 바로 채팅 시작 (+ ENTRY-5 사이드바 `+` 행)
2. **ENTRY-3** Cmd+K 유니버설 런처
3. **CHAT-10** In-chat 검색 + **CHAT-12** Branch from here
4. **CHAT-3** 도구 호출 밀도 제어 + **CHAT-5** 시간 마커
5. **SIDE-1** 사이드바 검색 + **MCP-3** Recently used tools

---

# § ENTRY — 채팅 진입 흐름

## ENTRY-1 ⭐🔥 카드에서 바로 채팅 시작

**상태**: accepted (commit 다음)

**Rework note (1차 테스트 후)**: 카드 전체 클릭 = 세션 생성 방식은 매번
새 세션을 만들어 누적되는 부작용이 큼. 기존 세션 resume 의도가 사라짐.
→ 카드 클릭은 detail 페이지로 (browse), 별도 "Start chat" 버튼 클릭만
세션 생성으로 분리. (원래 제안 시점의 대안 A로 전환)

**최종 동작**:
- 카드 본체 클릭 → `/agents/{id}` (detail, resume용)
- "Start chat" 버튼 → 새 세션 생성 + `/sessions/{id}`
- cmd/middle-click → detail 새 탭 (Link 유지)

현재 `/agents` 그리드 → 카드 클릭 → `/agents/{id}` detail 페이지 →
"New Chat" 버튼 → `/sessions/{id}`. 4 클릭, 3 페이지 전환.

**제안**:
- agent-card 자체 클릭 = 즉시 세션 생성 + `/sessions/{id}`로 이동
- detail 페이지로 가는 진입은 카드 hover시 노출되는 작은 `⋯` 또는 "Open" 버튼
- agentsApi.createSession 직접 호출

**임팩트**: 첫인상 마찰 50% 감소.

---

## ENTRY-2 🔥 Quick-start 시트 (모달)

**상태**: rejected

**Reject reason**: ENTRY-1 (Start chat 버튼) + ENTRY-4 (detail 대시보드의
hero CTA + recent sessions) + ENTRY-5 (사이드바 + 버튼)이 합쳐서 같은 진입
경로를 이미 커버. 모달 시트는 추가 인지 부담만 늘리고 가치가 중복됨.

빈 채팅창 진입의 인지 부담("뭘 물어봐야 하지?")을 제거하기 위해
agent 클릭시 풀페이지 이동 대신 하단 슬라이드 시트.

**제안**:
- 하단에서 슬라이드 업되는 sheet 컴포넌트
  - 상단: agent 이름/아이콘/설명
  - 중간: "What do you want to do?" 텍스트 입력 (autofocus)
  - 하단: 최근 세션 3개 (resume 버튼)
- Enter → 세션 생성 + 첫 메시지 전송 + 이동

**의존성**: ENTRY-1과 둘 중 하나 선택. 둘 다 도입할 수도 있음.

---

## ENTRY-3 ⭐🔥 Cmd+K 유니버설 런처

**상태**: rejected

**Reject reason (2026-04-10)**: 1차 구현 후 사용자 평가 — 현재 워크플로 기준
필요성 대비 코드 무게가 큼. cmdk 의존성, 5개 신규 파일, provider 추가가
정당화될 만큼의 사용 빈도가 예상되지 않음. 사이드바 검색(SIDE-1)과 사이드바
세션 그룹 자체가 이미 비슷한 역할을 커버.

향후 재고려 트리거: 세션이 50개+ 되거나, 다른 영역(설정/명령) 진입이
복잡해져서 중앙 명령창의 가치가 명확해질 때.

Raycast의 본질. 어디서든 `⌘K` → 중앙 floating palette.

**제안**:
- 통합 검색: 에이전트 + 세션 + 명령
- 에이전트 선택 → 그 자리에서 메시지 타이핑 → Enter → 세션 생성 + 전송
- shadow-5 + glow-warm 활용 (이미 구현됨)
- 기존 `useHotkey` hook 사용
- `cmdk` 라이브러리 도입 검토 또는 자체 구현

**임팩트**: "키보드로 굴러가는 도구" 정체성 확립.

---

## ENTRY-4 detail 페이지 → 대시보드化

**상태**: accepted

**v1 범위**: hero (icon + name + Start chat CTA), Recent Sessions (top 5 + view all),
Configuration grid (기존 4개 카드). Suggested prompts/Stats는 백엔드 의존이라 보류.
페이지를 4개 컴포넌트로 분리: hero / recent-sessions / config-grid / page assembler.

현재 `/agents/{id}` detail 페이지는 read-only 메타 정보 카드 무덤.

**제안**:
```
┌─ Hero: 이름 + [⌘N New Chat] CTA
├─ Recent sessions (5개, click to resume)
├─ Suggested prompts ("Try asking…") — instruction에서 발췌
├─ Stats: 총 세션 수, 마지막 사용일, 평균 길이
└─ Configuration (collapsible)
```

**의존성**: ENTRY-1이 먼저 들어가면 detail 페이지 진입 빈도가 줄어드므로
 우선순위가 낮아짐.

---

## ENTRY-5 ⭐ 사이드바 "+ New chat" 행

**상태**: accepted

**Bug fix during testing**: useCreateSession 훅이 success path에서 creating
상태를 false로 안 돌려놨음 — 사이드바는 unmount되지 않으니 spinner 무한
회전. `finally` 블록으로 항상 reset하도록 수정.

**구현**: agent 그룹 헤더에 hover-revealed `+` 버튼. ENTRY-1, ENTRY-4와 공유하는
`useCreateSession` 훅 사용. 삭제된 agent에는 안 보임.

활성 세션 그룹 헤더 옆 작은 `+` 버튼 → 한 클릭으로 같은 agent 새 세션.

**파일**: `features/layout/components/sidebar/sidebar-agent-group.tsx`

---

# § MCP — 도구 검색/선택

## MCP-1 🔥 Two-pane 레이아웃

**상태**: pending

현재 accordion (서버 펼침/접힘) 구조는 도구 발견성이 낮음.

**제안**:
```
┌──────────┬─────────────────────────────┐
│ Servers  │ Tools                       │
│ ─ All    │ ┌──────┐ ┌──────┐ ┌──────┐ │
│ ─ Recent │ │ Card │ │ Card │ │ Card │ │
│ ─ github │ └──────┘ └──────┘ └──────┘ │
│ ─ jira   │ ...                         │
└──────────┴─────────────────────────────┘
[12 tools selected]              [Done]
```

**파일**: `features/agents/components/tool-selector/tool-selector.tsx` 전면 재설계.

---

## MCP-2 ⭐ 도구 = 카드, 행이 아님

**상태**: pending

각 카드:
- 아이콘 + qualified_name
- 2줄 description (line-clamp)
- 작은 태그: input schema 키 ("repo, issue, body")
- ✓ Add 버튼
- Hover → 우측에 풀 description + 예시 호출 popover

**파일**: `tool-row.tsx` → `tool-card.tsx`로 재작성.

**의존성**: MCP-1과 함께 진행.

---

## MCP-3 ⭐🔥 Recently used tools

**상태**: pending

같은 도구를 여러 에이전트에 붙이는 게 작업의 80%인데 매번 검색하는 비효율.

**제안**:
- localStorage에 최근 선택한 tool_id 저장
- 다이얼로그 열면 최상단에 "Recently used" 섹션 자동 노출

**파일**: `lib/storage/recently-used-tools.ts` (신규) + tool-selector 수정.

---

## MCP-4 카테고리 필터 칩

**상태**: pending

도구의 자연 분류: Files, Network, Search, Database, Communication...

**제안**:
- 칩 클릭으로 한 번에 좁히기
- 백엔드에 카테고리 필드가 없으면 server name + tool name 휴리스틱으로 클라이언트 자동 분류

---

## MCP-5 서버 일괄 선택

**상태**: pending

서버 카드에 "Add all 12 tools" 버튼.
"이 서버는 통째로 신뢰" 사용자가 의외로 많음.

---

## MCP-6 컨텍스트 추천

**상태**: pending

agent 이름/description에 "code", "review" → github, files 우선 정렬.
ML 없이 키워드 매칭 휴리스틱만으로 충분.

---

## MCP-7 폼 inline preview

**상태**: pending

현재 선택된 도구 칩에 hover → tooltip으로 description.

**파일**: `features/agents/components/form/tools-section.tsx`

---

## MCP-8 도구 사용량 표시

**상태**: pending

도구 카드에 작은 텍스트: "Used in 3 of your agents".
백엔드 API 추가 필요할 수 있음.

---

# § CHAT — 채팅창 너비 / 가독성 / 히스토리

## CHAT-1 ⭐ 콘텐츠 적응형 너비

**상태**: pending

기본 720px (prose 친화), 메시지에 코드 블록 / wide tool 출력 있으면 자동 920px로 확장.

**파일**: `features/chat/components/message-list/message-list.tsx`,
`features/chat/components/message-list/agent-bubble.tsx`

---

## CHAT-2 너비 토글 버튼

**상태**: pending

헤더에 `[narrow] [comfort] [wide]` segmented control. localStorage 저장.

**파일**: `chat-header.tsx`

---

## CHAT-3 🔥 도구 호출 밀도 제어

**상태**: accepted

**v1 범위**: 연속 3개+ tool call을 자동 그룹화. 카드 → 텍스트 칩으로 바뀜
(rework 1차 후). 펼친 도구는 Fragment 자식으로 부모 flex의 직접 자식이
되어 ungrouped tool call과 같은 depth로 렌더. Sub-agent nested children과
시각적 충돌 해소.

**Bonus tweak**: ThinkingChip도 같은 칩 패턴으로 톤 다운 (warning yellow →
fg-disabled, 카드 → 텍스트, 항상 default collapsed). 별도 백로그 아이템 없이
동일 commit에 포함.

긴 세션이 ToolCallCard 벽이 되는 가장 큰 가독성 문제.

**제안**:
- 완료된 tool call은 기본 collapsed (헤더만)
- 연속 3개+ tool call은 자동 그룹화: `▶ 12 tool calls` 단일 행
- 메시지별 토글: "Hide tools" / "Show tools"

**파일**: `tool-call-card.tsx`, `streaming-response.tsx`, `agent-bubble.tsx`

---

## CHAT-4 ⭐ 메시지 그룹화 (consecutive sender)

**상태**: pending

같은 sender 연속 메시지는 첫 메시지에만 아바타.
2번째부터는 들여쓰기 정렬, 아바타 자리 비움.

**파일**: `message-list.tsx`, `user-bubble.tsx`, `agent-bubble.tsx`

---

## CHAT-5 🔥 시간 마커

**상태**: pending

- 메시지 간 간격 > 10분 → 가운데 정렬 divider ("3 hours later")
- 세션 spans days → sticky date header ("Yesterday", "March 12")

**파일**: `message-list.tsx` + 새 컴포넌트 `time-divider.tsx`

---

## CHAT-6 메시지 액션 행 (hover)

**상태**: pending

모든 메시지 hover → 우측 작은 액션 row:
- Copy (이미 있음)
- Quote (`> ...` 형식으로 입력창 자동 삽입)
- Branch from here (CHAT-12와 연계)
- Permalink (CHAT-11과 연계)
- Bookmark

**파일**: `message-list/` 컴포넌트들 + 새 `message-actions.tsx`

---

## CHAT-7 코드 블록 강화

**상태**: pending

- 첫 줄 헤더: `📄 src/foo.ts` (파일명) | `bash` (언어) + [Copy] [Wrap] [Expand]
- Edit tool 결과는 diff 하이라이트 (red/green)
- 긴 줄 wrap 토글
- bash → "Copy as command"

**파일**: `features/chat/components/markdown/code-block.tsx`

---

## CHAT-8 마크다운 시각 위계 강화

**상태**: pending

현재 H1-H3가 거의 동일 사이즈. 큰 답변일수록 위계 차이가 가독성에 결정적.

**제안**:
- H1: 18 → 20px
- H2: 16 → 17px
- H3: 14px bold
- DESIGN.md type 클래스 활용

**파일**: `globals.css` (markdown-body 섹션)

---

## CHAT-9 ⭐ 사용자 / 에이전트 비대칭 너비

**상태**: pending

- 사용자: 60% (오른쪽 끝) — 짧은 입력
- 에이전트: 88% (왼쪽 끝) — 길고 구조화된 출력
- 현재 둘 다 75%

**파일**: `user-bubble.tsx`, `agent-bubble.tsx`

---

## CHAT-10 🔥 In-chat 검색 (Cmd+F 가로채기)

**상태**: pending

`⌘F` → 채팅 상단 검색바 슬라이드 다운.
- 매치 하이라이팅 + 다음/이전
- collapsed tool cards 안의 텍스트도 검색

**파일**: 신규 `features/chat/components/chat-search.tsx`,
`use-chat-search.ts` hook, `chat-view.tsx`에 통합

---

## CHAT-11 ⭐ 메시지 permalink

**상태**: pending

메시지 hover → "Copy link" → `/sessions/{id}#msg-{messageId}`.
페이지 로드시 해당 메시지로 자동 스크롤 + 잠시 하이라이트.

**파일**: `message-list.tsx`, `chat-view.tsx`

---

## CHAT-12 🔥 Branch / Fork from message

**상태**: pending

이전 사용자 메시지 hover → "Edit & branch".
그 시점부터 fork된 새 세션 생성.

**의존성**: 백엔드 API 필요 (`POST /sessions/{id}/branch?from_message_id=...`).
백엔드 협의 후 진행.

---

## CHAT-13 Jump navigation rail

**상태**: pending

우측 얇은 mini-map 레일. 메시지마다 dot, 색상으로 종류 구분.
hover preview, 클릭 점프. 100+ 메시지 세션에 결정적.

**파일**: 신규 `features/chat/components/jump-rail.tsx`

---

## CHAT-14 "Show earlier messages" pagination

**상태**: pending

긴 세션 진입시 최근 N개만 렌더, 위에 "Show earlier" 버튼.
가상화 도입 전 단계.

**파일**: `message-list.tsx`

---

# § SIDE — 사이드바

## SIDE-1 🔥 사이드바 검색

**상태**: pending

사이드바 최상단에 검색바.
- 세션 제목 + 메시지 내용 동시 검색 (백엔드 API 필요할 수 있음)
- 50+ 세션 사용자에게 결정적

**파일**: `features/layout/components/sidebar/sidebar-search.tsx` (신규),
`sidebar.tsx`에 통합

---

## SIDE-2 🔥 그룹화 토글: By Agent / By Date

**상태**: pending

현재 "By Agent"만 가능. "By Date" 모드: Today / Yesterday / This week / This month / Older.
사람들이 실제로 떠올리는 방식.

**파일**: `sidebar-provider.tsx` (그룹화 모드 상태),
`sidebar-sessions.tsx` (양쪽 렌더링)

---

## SIDE-3 ⭐ Pin / Star

**상태**: pending

세션 ⋯ → "Pin to top". "Pinned" 섹션이 사이드바 최상단.
백엔드에 `pinned_at` 컬럼 추가 필요.

---

## SIDE-4 ⭐ Hover preview

**상태**: pending

세션 항목 hover → tooltip에 last user message snippet.

**파일**: `sidebar-session-item.tsx`

---

## SIDE-5 Bulk 작업

**상태**: pending

shift-click 다중 선택, bulk delete/archive/export.

---

## SIDE-6 ⭐ Streaming 시각화 강화

**상태**: pending

다른 세션이 응답 중이면 사이드바 행 자체가 미세하게 pulse + spinner.
백그라운드 작업 알림성 부족 해소.

**파일**: `sidebar-session-item.tsx`

---

## SIDE-7 Unread bubble 명확화

**상태**: pending

마지막 본 시점 이후 새 메시지 수 + dot.
클릭하면 unread 카운터 리셋.

---

# § INPUT — 입력 영역

## INPUT-1 🔥 Slash commands

**상태**: pending

`/` 입력시 명령 dropdown:
- `/clear` — 새 세션 시작
- `/export pdf|md`
- `/cancel`
- `/branch`
- `/think`
- `/agent {slug}`

**파일**: 신규 `features/chat/components/input/slash-commands.tsx`,
`chat-input.tsx`에 통합

---

## INPUT-2 ⭐ 단축키 cheat sheet

**상태**: pending

입력창 우측 하단 `?` 아이콘 → 단축키 모달 (Kbd 컴포넌트 활용).

**파일**: 신규 `features/chat/components/shortcuts-dialog.tsx`

---

## INPUT-3 Voice input

**상태**: pending

Web Speech API → STT → 입력창 채움. 마이크 버튼 추가.

---

## INPUT-4 Smart paste

**상태**: pending

URL paste → "Fetch this URL?" 칩 제안 (WebFetch 자동).
파일 경로 paste → "Read this file?" 제안.

---

## INPUT-5 🔥 Retry on error

**상태**: pending

에러 메시지 옆에 "Retry" 버튼. 직전 user 메시지 그대로 재전송.

**파일**: `agent-bubble.tsx`, `use-chat-messages.ts`

---

## INPUT-6 File dropzone (visual placeholder)

**상태**: pending

백엔드 첨부 지원 전에도 dropzone UI 마련.
"Drop files here to attach" hover state.

---

# § CONN — 연결 / 알림

## CONN-1 ⭐ 상태 표시 미니멀화

**상태**: pending

- 정상시: dot만, 라벨 없음
- 비정상 (offline / connecting > 1s): top-of-page progress bar (Vercel 스타일)

**파일**: `chat-header.tsx`, `chat-status-banner.tsx`

---

## CONN-2 🔥 자동 재연결

**상태**: pending

끊김 → 자동 재시도 + 토스트 알림. (인프라는 깔아둠 — 적용만 필요)

**파일**: `use-session-websocket.ts`, `lib/ws/session-socket.ts`

---

## CONN-3 취소 후 undo

**상태**: pending

"Generation cancelled" 토스트 + "Undo (regenerate)" 버튼.

**의존성**: 토스트 시스템이 먼저 필요 (또는 inline UI로).

---

# § POLISH — 디자이너 노트 (작은 것들)

## POLISH-1 에이전트 아이콘 picker

**상태**: pending

이모지 picker 또는 lucide 아이콘 + 색상 선택.

**파일**: `features/agents/components/form/basic-info-section.tsx`

---

## POLISH-2 🔥 세션 자동 제목 LLM 생성

**상태**: pending

첫 user 메시지의 첫 줄을 자르는 현재 방식은 어색.
첫 응답 후 LLM에게 "summarize in 5 words" 호출 (ChatGPT 방식).

**의존성**: 백엔드 API 또는 클라이언트에서 LiteLLM 직접 호출.

---

## POLISH-3 에이전트 README 슬롯

**상태**: pending

agent에 markdown README 필드 추가 → detail 페이지에 렌더.
"이 에이전트 어떻게 쓰는지" 설명 자리.

**의존성**: 백엔드 schema 변경 (Agent 모델에 readme 필드 추가).

---

## POLISH-4 빈 상태 일러스트

**상태**: pending

EmptyState가 모두 단조로운 lucide 아이콘. 페이지별 맞춤 일러스트.

---

## POLISH-5 에러 메시지 톤 개선

**상태**: pending

"Error: ..." raw 텍스트 그대로 노출 중. 친근하게 wrapping + retry 액션.

**파일**: `use-chat-messages.ts`의 error case handler,
`features/chat/components/error-message.tsx` (신규)

---

## (새 아이디어가 떠오르면 여기에 추가)
