/**
 * Deterministic tone selection from a stable id (UUID, slug, etc.).
 *
 * Tone is part of the asset's identity — once an agent/workflow has been
 * shown with a tone, the same id must always produce that same tone. We
 * derive it from a hash of the id rather than storing it on the record;
 * the backend doesn't need to know about presentation.
 */

export const TONES = [
  "blue",
  "green",
  "amber",
  "pink",
  "purple",
  "teal",
  "rose",
  "slate",
] as const;

export type Tone = (typeof TONES)[number];

export function toneFromId(id: string | null | undefined): Tone {
  if (!id) return "slate";
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (Math.imul(31, h) + id.charCodeAt(i)) >>> 0;
  }
  return TONES[h % TONES.length];
}

/** First grapheme of a name, uppercased; fallback to "?". */
export function initialFromName(name: string | null | undefined): string {
  const trimmed = (name ?? "").trim();
  if (!trimmed) return "?";
  return trimmed.slice(0, 1).toUpperCase();
}
