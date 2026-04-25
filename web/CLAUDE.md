# Aviary Web — Project Instructions

This file scopes Claude Code's behavior when touching the **web** workspace. The repo-wide [CLAUDE.md](../CLAUDE.md) covers backend / infra; this one is UI-focused.

## What this app is

Internal platform for building, running, and sharing AI **agents** and **workflows**. Five primary surfaces:

- **Dashboard** (`/`) — at-a-glance: recent sessions, recent runs, your reach
- **Agents** (`/agents`, `/agents/[id]`) — list → chat home → editor / detail
- **Workflows** (`/workflows`, `/workflows/[id]`) — list → overview → builder / runs
- **Marketplace** (`/marketplace`) — discover/install (mock data today)
- **Settings** (`/settings`) — profile · credentials · preferences (theme toggle)

Plus overlays: ⌘K command palette, notifications dropdown, user menu.

Ownership states for every asset: **private** (mine, unpublished), **published** (mine, on marketplace), **imported** (someone else's, installed).

## Stack

- Next.js 15 App Router + React 19
- Tailwind 3 + `tailwindcss-animate` + `@tailwindcss/typography`
- shadcn/ui (style: `new-york`, base: `neutral`, CSS vars on)
- `@xyflow/react` (workflow graph), `@monaco-editor/react`, `react-diff-viewer-continued`, `@dnd-kit/*`, `lucide-react`
- Fonts: Inter (UI) + JetBrains Mono (code) via `next/font` ([src/app/fonts.ts](src/app/fonts.ts))

## Design system — "Aviary Slate"

The full spec lives at **[design-system/](./design-system/)** — read it before touching UI:

- [design-system/README.md](./design-system/README.md) — entry point + principles
- [design-system/tokens.md](./design-system/tokens.md) — colors, borders, shadows, radius, tone palette, alpha-modifier caveat
- [design-system/typography.md](./design-system/typography.md) — Inter scale, `t-*` classes, tabular nums
- [design-system/screens.md](./design-system/screens.md) — per-route specs and the file owning each
- [design-system/components.html](./design-system/components.html) — visual primitive reference (open in a browser)

### Hard rules (enforced)

1. **No inline hex.** Use Slate tokens via Tailwind aliases (`bg-canvas`, `text-fg-primary`, `border-border-subtle`) or `var(--token)`. The exception is workflow node category colors and chat-export PDF/HTML strings.
2. **No gradients on chrome or text.** Tone avatars are solid tinted fills.
3. **No emoji.** Use `lucide-react` (re-exported from [components/icons](src/components/icons/index.tsx)).
4. **Tabular numerals on every number** (`font-variant-numeric: tabular-nums` or `.num` / `t-mono`).
5. **Hover = subtle tone shift** via `bg-hover` / `bg-active`. Never a color swap.
6. **Active nav** = 2px left rail in `--accent-blue`, not a filled pill.
7. **Density over breathing room.** Header 48px, row heights 32-40px, card padding 14-16px.
8. **Light theme is real.** Verify in Settings → Preferences → Light before merging UI changes. No `bg-white/[…]` or other dark-only hardcodes.
9. **Tone is identity.** Derive deterministically from the asset id via [lib/tone.ts](src/lib/tone.ts) — never re-roll, never store on the record.

### Tailwind alpha caveat

`bg-X/50` only works on RGB-channel colors. Slate tokens (`fg-*`, `accent`, `status-*`) emit hex/rgba directly, so `bg-fg-secondary/50` is silently dropped. Use the legacy `info / success / danger / warning / elevated` palette when you need alpha; full details in [tokens.md](./design-system/tokens.md#alpha-modifier-caveat).

## Routing

Use Next.js App Router. Screen state that needs to be deep-linkable (active session, workflow tab, settings tab) goes into `?query=` parameters via `useSearchParams` / `router.replace`. Don't introduce a context-driven RouteProvider.

Routes are declared in [lib/constants/routes.ts](src/lib/constants/routes.ts) — never hand-build a path string.

## Naming & file layout

```
src/
  app/
    (authenticated)/      # AppShell-wrapped pages
      page.tsx            # Dashboard
      agents/
      workflows/
      marketplace/
      settings/
    layout.tsx            # ThemeProvider + AuthProvider + fonts + globals
  components/
    ui/                   # shadcn primitives — must match components.html
    feedback/             # Empty/Error/Loading
    icons/                # lucide re-export
    brand/                # Logo, etc.
  features/
    agents/  workflows/  marketplace/  chat/  command-palette/
    notifications/  settings/  theme/  layout/  search/  workspace/
      api/          # thin fetch wrappers over lib/http
      components/
      hooks/
      providers/   (when context-shaped)
  hooks/                  # cross-cutting
  lib/                    # http, ws, auth, tone, utils, constants
  types/                  # one file per domain
```

**Rule**: a component used by one feature lives under `features/<name>/components/`. Used by 2+ → promote to `components/`.

**Component naming**: PascalCase file, named export matching the file (`AgentCard.tsx` → `export function AgentCard()`).

**Hooks**: `use-*.ts(x)`, named export `useFoo`.

**API clients**: never call `fetch` from a component. Each domain has `features/<name>/api/<name>-api.ts` wrapping [lib/http](src/lib/http). Mocks go in `_mocks.ts` adjacent to the API.

## Commands

- `npm run dev` — Next dev on `:3000` (already running in compose; container reloads from this dir bind-mount)
- `npm run build` — full typecheck + production bundle (run before any commit that touches >1 file)
- `npm run lint`

## When in doubt

The design-system docs are the tiebreaker. If a doc and the code disagree, the doc is the spec — fix the code or update the doc, but never both casually.
