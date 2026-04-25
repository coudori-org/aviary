# Aviary Slate — Design Tokens

All tokens are CSS custom properties defined in [src/app/globals.css](../src/app/globals.css). They switch between light and dark via `:root[data-theme="dark|light"]`. An optional `:root[data-accent="green"]` swaps the accent hue.

**Usage rule**: never inline hex values in components. Reference the Tailwind alias (defined in [tailwind.config.ts](../tailwind.config.ts)) or `var(--token-name)` directly.

---

## Canvas & surfaces (dark)

| Token | Value | Usage |
|---|---|---|
| `--bg-canvas` | `#0F1115` | Outermost app bg, header, main scroll area |
| `--bg-surface` | `#14161C` | Sidebar, side panels, persistent chrome |
| `--bg-raised` | `#191C23` | Cards, popovers, dialogs, chat bubbles |
| `--bg-sunk` | `#0B0D11` | Inputs, code blocks, workflow canvas |
| `--bg-hover` | `rgba(255,255,255,0.04)` | Hoverable row / button overlay |
| `--bg-active` | `rgba(255,255,255,0.07)` | Active / pressed / selected |
| `--bg-overlay` | `rgba(8,10,14,0.72)` | Dimmer behind modals & palette |

## Canvas & surfaces (light)

| Token | Value | Usage |
|---|---|---|
| `--bg-canvas` | `#FAF9F7` | Warm off-white — never pure white |
| `--bg-surface` | `#F4F2EE` | Sidebar, side panels |
| `--bg-raised` | `#FFFFFF` | Cards, dialogs, chat bubbles |
| `--bg-sunk` | `#EDEAE4` | Inputs, code blocks, workflow canvas |
| `--bg-hover` | `rgba(20,22,28,0.04)` | — |
| `--bg-active` | `rgba(20,22,28,0.07)` | — |
| `--bg-overlay` | `rgba(60,55,45,0.20)` | Warm-toned dimmer |

## Borders

Three levels — `rgba(white, α)` in dark, `rgba(60,55,45, α)` in light.

| Token | Dark α | Light α | Usage |
|---|---|---|---|
| `--border-subtle` | 0.06 | 0.08 | Section dividers, card outline |
| `--border-default` | 0.09 | 0.12 | Inputs, buttons, most borders |
| `--border-strong` | 0.15 | 0.22 | Hover-state borders |

## Foreground (text)

| Token | Dark | Light | Usage |
|---|---|---|---|
| `--fg-primary` | `#ECEDF0` | `#1B1D22` | Body text, headings |
| `--fg-secondary` | `#B4B7C0` | `#4E525C` | Secondary labels, sidebar inactive |
| `--fg-tertiary` | `#878A94` | `#6F7380` | Metadata, timestamps |
| `--fg-muted` | `#5E616C` | `#9A9EA8` | Disabled, placeholder, overline |
| `--fg-inverse` | `#0F1115` | `#FAF9F7` | Text on filled primary button |

## Accent (primary interactive)

| Token | Dark | Light | Usage |
|---|---|---|---|
| `--accent-blue` | `#5B8DEF` | `#3B6FD8` | Primary buttons, links, focus |
| `--accent-blue-strong` | `#7BA5F5` | `#2E5BBF` | Hover state on primary |
| `--accent-blue-soft` | rgba 14% | rgba 10% | Focus ring, ghost active |
| `--accent-blue-border` | rgba 35% | rgba 30% | Focused input border |

Optional `data-accent="green"` swaps to `#2FA46A` / `#3FB57B`.

## Status

| Token | Dark | Light | Semantic |
|---|---|---|---|
| `--status-live` | `#4ADE80` | `#2FA46A` | Running, online, success |
| `--status-warn` | `#F5B454` | `#C9801E` | Warning, pending |
| `--status-error` | `#F07A7A` | `#D25151` | Failed, error |
| `--status-info` | `#5B8DEF` | `#3B6FD8` | Informational (same as accent) |

Each has a `-soft` variant at ~12-15% alpha for pills, backgrounds, and dot halos.

## Ownership badges

Badge background + foreground, used by [components/ui/kind-badge.tsx](../src/components/ui/kind-badge.tsx).

| Token | Dark | Used by |
|---|---|---|
| `--badge-private-bg` / `-fg` | neutral 10% / `#B4B7C0` | Private assets |
| `--badge-published-bg` / `-fg` | blue 15% / `#95B4F5` | Published assets |
| `--badge-imported-bg` / `-fg` | green 13% / `#7DDC9E` | Imported assets |

## Shadows

All shadows pair with a hairline border via a second layer.

| Token | Value (dark) |
|---|---|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.35)` |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,0.40), 0 0 0 1px rgba(255,255,255,0.04)` |
| `--shadow-lg` | `0 12px 32px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.06)` |
| `--shadow-xl` | `0 24px 56px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.08)` |

Light theme shadows are warm-toned (`rgba(60,55,45, …)`) and softer.

---

## Non-token constants

These never change by theme:

**Radius**: 4 · 5 · 6 · 7 · 10 · 12 · 99 (pill)
- 7px — buttons, inputs
- 10px — cards
- 12px — dialogs, palette

**Spacing**: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 56 · 72

**Transition**: `120ms` for hovers, `180ms cubic-bezier(0.16,1,0.3,1)` for panel slides, `220ms` for dialog enter/exit.

**Focus ring**: `0 0 0 3px var(--accent-blue-soft)` — never an outline.

---

## Tone palette (identity colors)

8 tones for agent / workflow avatars. Each = tinted background + saturated foreground. Assigned deterministically from the asset id ([lib/tone.ts](../src/lib/tone.ts)) — never re-rolled, never stored on the record.

Tones: `blue`, `green`, `amber`, `pink`, `purple`, `teal`, `rose`, `slate`.

Rendered via `.tone-<name>` CSS classes that set both `background` and `color`. Use the `Avatar` primitive at [components/ui/avatar.tsx](../src/components/ui/avatar.tsx).

---

## Tailwind aliases

[tailwind.config.ts](../tailwind.config.ts) exposes Slate tokens as first-class colors:

```ts
colors: {
  canvas: "var(--bg-canvas)",
  surface: "var(--bg-surface)",
  raised: "var(--bg-raised)",
  sunk: "var(--bg-sunk)",
  hover: "var(--bg-hover)",
  active: "var(--bg-active)",
  overlay: "var(--bg-overlay)",

  border: {
    subtle: "var(--border-subtle)",
    DEFAULT: "var(--border-default)",
    strong: "var(--border-strong)",
  },

  fg: {
    primary: "var(--fg-primary)",
    secondary: "var(--fg-secondary)",
    tertiary: "var(--fg-tertiary)",
    muted: "var(--fg-muted)",
  },

  accent: {
    DEFAULT: "var(--accent-blue)",
    soft: "var(--accent-blue-soft)",
    border: "var(--accent-blue-border)",
  },

  status: {
    live: "var(--status-live)",
    warn: "var(--status-warn)",
    error: "var(--status-error)",
    info: "var(--status-info)",
  },
}
```

shadcn's `primary / secondary / destructive / muted / accent` aliases also map onto these in `globals.css` under `@layer base`.

### Alpha modifier caveat

Tailwind's `bg-X/50` alpha modifier **only works on RGB-channel colors** (`rgb(var(--legacy-X) / <alpha-value>)` form). Slate tokens use `var(--xx)` and emit hex/rgba directly, so `bg-fg-secondary/50` and similar will be silently dropped.

For hairline tints / overlays prefer:
- `bg-hover` / `bg-active` (built-in subtle layers)
- legacy `info / success / danger / warning / elevated` (RGB-channel, alpha works)

If a brand-new alpha-aware Slate token is needed, add it to `globals.css` as `--token-rgb: R G B;` and a Tailwind alias `rgb(var(--token-rgb) / <alpha-value>)`.
