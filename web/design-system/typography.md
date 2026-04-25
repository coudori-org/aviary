# Aviary Slate — Typography

Two faces: **Inter** for UI, **JetBrains Mono** for code/keyboard hints.
Both variable fonts, loaded through `next/font` (see `src/app/fonts.ts`).

```ts
// src/app/fonts.ts
import { Inter, JetBrains_Mono } from "next/font/google";

export const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});
```

Applied in `<html>` once:

```tsx
<html className={`${inter.variable} ${jetbrainsMono.variable}`}>
```

`globals.css` wires the variables into `body` and `code`.

---

## Base

```css
body {
  font-family: var(--font-inter), ui-sans-serif, system-ui, sans-serif;
  font-size: 13.5px;
  line-height: 1.5;
  font-feature-settings: "cv11", "ss01", "cv02";
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

code, pre, .mono {
  font-family: var(--font-mono), ui-monospace, SFMono-Regular, monospace;
  font-size: 12.5px;
}
```

**Base size is 13.5px, not 16.** This is a density-first tool, not a
marketing site. Don't raise it.

**Feature settings** `cv11 ss01 cv02` give Inter's slightly humanist
alternates — open `g`, single-story `a`, angled `l`. Keeps the UI
approachable despite the low contrast.

---

## Scale

All classes defined in `globals.css`. Use the class, not raw sizes.

| Class | Size | Weight | Letter-spacing | Line-height | Use for |
|---|---|---|---|---|---|
| `.t-hero`  | 24px   | 600 | -0.015em | 1.2  | Page title in header, hero numbers |
| `.t-h1`    | 20px   | 600 | -0.012em | 1.25 | Section headings |
| `.t-h2`    | 16px   | 600 | -0.008em | 1.3  | Card titles, panel headings |
| `.t-h3`    | 14px   | 600 | -0.005em | 1.35 | Sub-sections, list group labels |
| `.t-body`  | 13.5px | 400 | 0        | 1.55 | Body text, descriptions |
| `.t-small` | 12.5px | 400 | 0        | 1.45 | Metadata, secondary labels, timestamps |
| `.t-xs`    | 11.5px | 500 | 0        | 1.4  | Chips, badges, tiny labels |
| `.t-over`  | 10.5px | 600 | 0.08em   | 1.3  | Overline / section label (UPPERCASE) |
| `.t-kbd`   | 11px   | 500 | 0        | 1    | Keyboard shortcut in `<Kbd>` |
| `.t-mono`  | 12.5px | 400 | 0        | 1.5  | Any monospaced inline |

### Tabular numerals

Every number UI — stats, counts, timestamps, file sizes, version tags —
uses `font-variant-numeric: tabular-nums`. Either apply the `.num` utility
class (defined in globals.css) or add it to the element directly. Misaligned
digits in a tool are unforgivable.

```css
.num { font-variant-numeric: tabular-nums; }
```

---

## Color pairings

| Class | Token | Typical element |
|---|---|---|
| `.fg-primary`   | `--fg-primary`   | Headings, primary text |
| `.fg-secondary` | `--fg-secondary` | Body when on a busy surface |
| `.fg-tertiary`  | `--fg-tertiary`  | Metadata, inactive nav |
| `.fg-muted`     | `--fg-muted`     | Placeholder, disabled, overline |
| `.fg-accent`    | `--accent-blue`  | Inline links, emphasized numbers |

`.t-over` sets `color: var(--fg-muted)` by default. Override sparingly.

---

## Compositions

Common pairings you'll write often:

```html
<!-- Stat block -->
<div class="t-over">Chat sessions</div>
<div class="t-hero num">284</div>
<div class="t-small fg-tertiary num">+12% this week</div>

<!-- Card title row -->
<div class="t-h2">PR Reviewer</div>
<div class="t-small fg-tertiary">Claude Sonnet 4.5 · 6 tools</div>

<!-- Nav item -->
<span class="t-body">Agents</span>
<span class="t-small fg-muted num">8</span>

<!-- Code -->
<code class="t-mono">src/features/auth/token-validator.ts:42</code>
```

---

## Don't

- Don't raise base size to 14 or 15 "for accessibility". Use your browser's
  zoom. The design is tuned for 13.5.
- Don't mix weights outside `400 / 500 / 600`. No 700, no 300.
- Don't `text-transform: uppercase` on anything except `.t-over`.
- Don't use Inter's default `1`, `I`, `l`. The `cv11` feature disambiguates;
  if it's missing, the feature settings weren't applied.
- Don't use serif anywhere. Don't load Fraunces / Playfair / etc.
- Don't animate font-size. Animate opacity or `transform: scale` on a
  container instead.

---

## Tailwind escape hatch

If you need a one-off size outside the scale, use Tailwind arbitrary values
but pair with `.num` when numeric:

```tsx
<div className="text-[11px] leading-[1.3] tracking-[0.06em] fg-muted">
  …
</div>
```

Any one-off that reappears 3+ times should become a new class in `globals.css`
instead — don't multiply arbitraries.
