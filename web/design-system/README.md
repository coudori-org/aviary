# Aviary Slate — Design System

This directory is the source of truth for Aviary's UI. The implementation lives under [src/](../src/); these files are the spec it must match.

## Files

- **[tokens.md](./tokens.md)** — Color/border/shadow/radius/spacing/tone palette. Explains how Slate tokens map to Tailwind aliases and the alpha-modifier caveat.
- **[typography.md](./typography.md)** — Inter + JetBrains Mono setup, the `t-*` scale, tabular numerals, color pairings.
- **[screens.md](./screens.md)** — Per-route specs (Dashboard, Agents, Workflows, Marketplace, Settings, overlays). Each section points at the file owning the implementation.
- **[components.html](./components.html)** — Live visual reference for the primitive set (button, input, badge, avatar, status-dot, kind-badge, …). Open in a browser; it's static.

## When to update

Update a doc here **the same commit** that introduces a UI shift:

- New primitive in `src/components/ui/` → entry in `components.html`.
- New token in `globals.css` → row in `tokens.md`.
- New / restructured route → section in `screens.md`.
- New type-* class → row in `typography.md`.

If the docs and code drift, the docs are wrong by default — they are the spec, but they only stay accurate if every contributor keeps them current.

## Design principles (enforced)

1. **No filler.** Every pixel earns its place.
2. **No gradients** on chrome or text. Tone avatars use solid tinted fills; buttons are flat.
3. **No emoji.** Use lucide-react icons. Match its 1.5px stroke / 24px grid for custom SVGs.
4. **Tabular numerals** on every number — `font-variant-numeric: tabular-nums` (or `.num`).
5. **Hover = subtle tone shift**, never a color swap. Use `bg-hover` / `bg-active`.
6. **Active nav** gets a 2px left rail in accent — not a filled pill.
7. **No rounded corners on dense UI** (sidebar items 7px; header / panels / graph canvas 0).
8. **Density over breathing room.** Header 48px, row heights 32-40px, card padding 14-16px.
9. **Light theme is real.** `npx next build` and toggle via Settings → Preferences before merging anything UI-touching. No `bg-white/[…]` or other dark-only hardcodes.
10. **Tone is identity.** Once an asset has a tone (derived from its id via [lib/tone.ts](../src/lib/tone.ts)) it never re-rolls.
