# Aviary Slate — Screen Specs

One section per route. For each: purpose, layout, and the file owning the implementation. Dimensions and visual rules below are normative — when you build a new screen, match them or update this doc.

All authenticated routes share the **AppShell** at [features/layout/components/app-shell.tsx](../src/features/layout/components/app-shell.tsx) — 220px collapsible sidebar + 48px header + main area. Header carries breadcrumb, ⌘K search pill, notifications bell, user avatar.

---

## 1. Dashboard — `/`

Owner: [app/(authenticated)/page.tsx](../src/app/(authenticated)/page.tsx) → [features/dashboard/](../src/features/dashboard/)

**Purpose**: At-a-glance summary of the user's recent work and reach.

```
┌─────────────────────────────────────────────────────────────┐
│ Page header — greeting + [+ New agent] [+ New workflow]     │
├─────────────────────────────────────────────────────────────┤
│ Stat row — 4 cards, equal width                             │
│   Chat sessions │ Workflow runs │ Published agents │ Reach  │
├─────────────────────────────────────────────────────────────┤
│ Two-column split: Recent sessions │ Recent runs             │
├─────────────────────────────────────────────────────────────┤
│ Reach strip — your published assets, install counts         │
└─────────────────────────────────────────────────────────────┘
```

**Don't add**: agent runs graph, tokens-used meter, sparklines, this-week timeline.

---

## 2. Agents list — `/agents`

Owner: [app/(authenticated)/agents/page.tsx](../src/app/(authenticated)/agents/page.tsx) → [features/agents/components/agents-list.tsx](../src/features/agents/components/agents-list.tsx)

```
┌─────────────────────────────────────────────────────────────┐
│ Header: "Agents"  · [Import]  [+ New Agent]                 │
├─────────────────────────────────────────────────────────────┤
│ Kind tabs (All · Private · Published · Imported)  · Search  │
│                                            · Grid/List      │
├─────────────────────────────────────────────────────────────┤
│ Featured strip — 3 big cards (Published)                    │
│ Category pills                                              │
│ AgentCard grid (3-col responsive)                           │
└─────────────────────────────────────────────────────────────┘
```

**Card states**:
- Private: no badge
- Published: "Published" badge + install count
- Imported: "Imported" badge + `@author` + update dot if new version

**Click**: navigate to `/agents/{id}` (chat home).

---

## 3. Agent detail

Owner: [app/(authenticated)/agents/[id]/page.tsx](<../src/app/(authenticated)/agents/[id]/page.tsx>) → [features/agents/components/detail/agent-chat-page.tsx](../src/features/agents/components/detail/agent-chat-page.tsx)

Default surface = chat. Edit lives at `/agents/{id}/edit`, detail at `/agents/{id}/detail`.

### 3a. Chat surface

3-pane layout — sessions rail (240px) · chat thread (flex) · workspace (340px, optional).

```
┌────────────┬───────────────────────────┬──────────────────┐
│ Sessions   │ Chat thread               │ Workspace (opt.) │
│ (240px)    │ (flex)                    │ (340px)          │
│            │                           │                  │
│ [+ New]    │ ChatHeader (back, title,  │ FileTree         │
│ Pinned     │   width toggle, print,    │ (resizable)      │
│ Today …    │   export, ws toggle)      │                  │
│            │ MessageList               │                  │
│            │ ChatInput                 │                  │
└────────────┴───────────────────────────┴──────────────────┘
```

**ChatActionsProvider** ([features/chat/hooks/chat-actions-context.tsx](../src/features/chat/hooks/chat-actions-context.tsx)) lets the outer `AgentSubHeader` host the inline title editor + print + export buttons + width toggle while `ChatView` runs with `hideHeader`.

**Workspace overlay**: clicking a file in the tree opens a Monaco editor that slides in from the right, pushing the tree to a narrow 220px column. Editor closes back to the 3-pane chat.

### 3b. Editor — `/agents/[id]/edit`

Agent definition editor — name, instruction, model, tools. Two columns: form (560px) + live preview/test on right.

### 3c. Detail page — `/agents/[id]/detail`

Stats, instruction excerpt, recent sessions, skills/MCP tools.

---

## 4. Workflows list — `/workflows`

Owner: [app/(authenticated)/workflows/page.tsx](../src/app/(authenticated)/workflows/page.tsx) → [features/workflows/components/workflows-list.tsx](../src/features/workflows/components/workflows-list.tsx)

Mirrors Agents list (kind tabs, featured strip, category, card grid). `WorkflowCard` shows node count, last-run status dot, last-run timestamp instead of tools/sessions.

---

## 5. Workflow detail

Owner: [app/(authenticated)/workflows/[id]/page.tsx](<../src/app/(authenticated)/workflows/[id]/page.tsx>) (builder) and `/detail`, `/runs` siblings.

### 5a. Overview — `/workflows/[id]/detail`

Header (name, kind badge, version), description, stat row (total runs, last status, avg duration, success rate), readonly graph thumbnail, recent runs strip.

### 5b. Builder — `/workflows/[id]`

```
┌─────────────────────────┬─────────────────────────────────────┐
│ Left panel (240px)      │  Toolbar (top)                      │
│  Tabs: Nodes · Runs ·   │                                     │
│        Settings         │  xyflow canvas (bg-sunk + dot grid) │
│                         │                                     │
│                         │                                     │
├─────────────────────────┤  Right panel (340px)                │
│  AI Assistant (bottom,  │   Tabs: Inspector · Test            │
│   collapsible 260px)    │   Inspector OR Test, never both     │
└─────────────────────────┴─────────────────────────────────────┘
```

Canvas is `bg-sunk`; surrounding panels are `bg-surface` so the work area reads as its own surface.

### 5c. Runs — `/workflows/[id]/runs`

Filterable list. Click a row → builder at that version with run trace surfaced in the right panel.

---

## 6. Marketplace — `/marketplace`

Owner: [app/(authenticated)/marketplace/page.tsx](../src/app/(authenticated)/marketplace/page.tsx) → [features/marketplace/components/marketplace-list.tsx](../src/features/marketplace/components/marketplace-list.tsx)

```
┌──────────┬──────────────────────────────────────────────────┐
│ Category │ Header: Marketplace                              │
│ rail     │ Kind tabs · "Published by me" · Search · Sort    │
│ (180px)  │ · Grid/List toggle                               │
│          ├──────────────────────────────────────────────────┤
│          │ Featured strip                                   │
│          │ MarketplaceCard grid                             │
└──────────┴──────────────────────────────────────────────────┘
```

Detail at `/marketplace/[id]` — hero (avatar, name, version, description, [Import]), left main (overview, required tools, changelog), right sidebar (author, stats).

Backend integration is mock today ([features/marketplace/api/_mocks.ts](../src/features/marketplace/api/_mocks.ts)) — only [marketplace-api.ts](../src/features/marketplace/api/marketplace-api.ts) needs swapping when REST lands.

---

## 7. Settings — `/settings`

Owner: [features/settings/](../src/features/settings/)

3 tabs (URL-synced via `?tab=…`): **Profile**, **Credentials**, **Preferences**.

- **Profile**: read-only mirror of IdP claims (`display_name`, `email`, `external_id`, created date).
- **Credentials**: per-user Vault keys (`anthropic-api-key`, `github-token`, `slack-token`, `jira-token`, `notion-token`) — connected/missing status. Mutations are "Coming soon" (Vault REST UI not yet built).
- **Preferences**: theme picker (Dark/Light), accent picker. Theme write is real — toggles `<html data-theme>` + persists to `localStorage`.

---

## Cross-cutting overlays

### Command palette (⌘K)

Owner: [features/command-palette/command-palette.tsx](../src/features/command-palette/command-palette.tsx)

640px dialog, blur backdrop. Three sections (Agents · Workflows · Sessions, 5 each). 180ms-debounced fetch — agents via `/catalog/search?q=`, workflows client-side filter, sessions via `searchApi.searchMessages` full-text. Match substrings highlighted with `<mark>` + accent-soft bg.

Keys: ↑/↓ navigate · ↵ select · Esc close. Hover → set active.

### Notifications dropdown

Owner: [features/notifications/notifications-panel.tsx](../src/features/notifications/notifications-panel.tsx) + [notifications-provider.tsx](../src/features/notifications/notifications-provider.tsx)

360px panel from bell icon. In-memory feed (max 50), no persistence yet. Kinds: `chat_reply`, `workflow_complete`, `workflow_failed`. Each row: tone avatar + title + desc + relative time + unread dot. Empty: "You're all caught up".

Today only `chat_reply` is wired — fired from `ChatView` when streaming ends and the document is hidden. Workflow terminal hooks land later.

### User menu

Owner: [features/layout/components/user-menu-stub.tsx](../src/features/layout/components/user-menu-stub.tsx)

260px panel from header avatar. User card · Settings link · theme quick-toggle · Sign out.

---

## Responsive behavior

Desktop tool, minimum supported width **1280px**. Below that show a "best viewed on a larger screen" notice — don't collapse to mobile, the density model breaks. Sidebar auto-collapses 220 → 56 below 1440px.

---

## When implementing a new screen

1. Open this doc and find the screen spec.
2. Open [components.html](./components.html) for the live primitive reference.
3. Compose from [components/ui/*](../src/components/ui) primitives first. Add a new primitive only when the same pattern appears 3+ times.
4. Pull data through a feature API client. If the backend endpoint doesn't exist yet, add a `_mocks.ts` adapter and swap later.
5. Match Slate principles: no gradients on chrome / no emoji / tabular numerals on every number / hover = subtle tone shift / active nav = 2px left rail.
