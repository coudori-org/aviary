# Aurora Glass

Premium consumer-AI feel. Translucent layered glass over a living aurora
backdrop — every surface floats, colour breathes.

## Palette

| Token | Value | Role |
|---|---|---|
| `--bg-canvas` | `#08091A` | Deep cinematic navy — not neutral black |
| `--bg-sunk` | `#0E1026` | Slight lift for carved-in inputs |
| glass-1 | `rgba(255,255,255,0.04)` | Frosted pane |
| glass-2 | `rgba(255,255,255,0.07)` | Elevated frosted pane |
| glass-3 | `rgba(255,255,255,0.10)` | Hover / active glass |
| `--fg-primary` | `#F5F6FA` | Text primary |
| `--fg-secondary` | `#C5C8D6` | Text secondary |
| `--fg-muted` | `#8289A1` | Muted labels |

## Aurora gradient system

Three brand gradients carry the identity — used on CTAs, avatars,
status wash, active nav, focus rings.

- `--aurora-a` — `violet #7B5CFF → pink #FF4FB8 → amber #FFB347` (primary)
- `--aurora-b` — `cyan #4FC9FF → mint #5CFFCC` (success / info)
- `--aurora-c` — `coral #FF7A59 → gold #FFD866` (warning / attention)

Each gradient has a `-soft` variant at ~18-22% alpha for background
washes. Solid fallbacks (violet, cyan, coral) are exposed under the
`aurora-*` tailwind colour scale for small UI elements where gradients
would look muddy.

## Surface hierarchy

1. `<AuroraBackdrop>` — fixed behind everything: three drifting blobs
   (40–60s cycles) at 120px blur, violet + pink + cyan, plus a faint SVG
   grain overlay at 3% opacity.
2. Canvas — transparent root; the aurora shows through at all times.
3. `.glass-pane` / `.glass-raised` / `.glass-deep` — semi-transparent
   walls with `backdrop-filter: blur(24px) saturate(140%)`. An
   `@supports` block keeps them readable on Safari TP without
   backdrop-filter.
4. Shadows — every elevated surface floats: layered drop shadow plus
   inset top highlight (`inset 0 1px 0 rgba(255,255,255,0.08)`). Level 5
   adds a violet outer glow to mark hero moments.
5. CTAs — aurora-A gradient fill, violet outer glow, continuous
   `aurora-sheen` shimmer, `translateY(-1px)` on hover.

## Motion

- 320ms `cubic-bezier(0.16, 1, 0.3, 1)` on most transitions.
- Hover = lift + amplify glow, never a color swap.
- `.animate-aurora-sheen` gives primary buttons a slow 8s gradient
  breathing cycle.
- `prefers-reduced-motion` cuts every animation.

## Radius scale

Softer than the other concepts: 6 / 8 / 10 / 14 / 20 / 28 / 36 px.
Everything is rounded; hard corners only on the sandbox canvas itself.

## Typography

Stayed on Inter (no new font deps). Headings go larger + slightly
relaxed letter-spacing, `font-feature-settings: "ss01", "ss03", "cv11"`
for alternate letterforms. Body at 14px / 1.65 line-height — breathes
more than Obsidian Mono's 1.4.

## What's intentionally different from the other concepts

- **vs Obsidian Mono** — where Obsidian earns its drama through
  monospace discipline and razor-thin hairlines, Aurora leans the
  opposite way: colour-drenched, soft, musical. Glass substitutes for
  Obsidian's "carved from a single block" rigidity.
- **vs Editorial Warm** — Editorial feels bookish and daylight; Aurora
  is cinematic night, the backdrop itself animates. No serif display
  face, no warm paper; colour carries the emotional weight instead.
- **vs Terminal Pro** — Terminal celebrates density and function keys;
  Aurora strips chrome in favour of translucent depth. Every surface is
  a floating pane, not a keycap.
