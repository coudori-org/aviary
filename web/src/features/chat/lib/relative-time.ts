/**
 * Relative-time labels for the message-list time-divider.
 *
 * Pure functions, no React, no Date library. The output is intentionally
 * minimal — see the table below for the rules. Edge cases default to the
 * absolute-date branch so we never produce ambiguous output.
 *
 * Rule table:
 *   gap ≤ MIN_GAP_MIN  → null (no divider)
 *   same day, < 60m    → "X min later"
 *   same day, ≥ 60m    → "X hours later"
 *   yesterday          → "Yesterday at HH:MM"
 *   ≤ 7 days ago       → "N days ago at HH:MM"
 *   else               → "Mon DD at HH:MM"
 */

const MIN_GAP_MS = 10 * 60 * 1000;

const MONTH_SHORT = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function formatTime(d: Date): string {
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

/**
 * Compute the divider label between a previous and current message.
 *
 * Returns `null` if no divider should be rendered (gap too small AND
 * same calendar day).
 */
export function computeTimeDividerLabel(
  prevIso: string,
  currentIso: string,
): string | null {
  const prev = new Date(prevIso);
  const curr = new Date(currentIso);
  const gapMs = curr.getTime() - prev.getTime();

  // Negative or zero gap → safety: no divider (shouldn't happen with sorted messages)
  if (gapMs <= 0) return null;

  const sameDay = startOfDay(prev) === startOfDay(curr);

  if (sameDay) {
    if (gapMs < MIN_GAP_MS) return null;
    const minutes = Math.round(gapMs / 60_000);
    if (minutes < 60) return `${minutes} min later`;
    const hours = Math.round(minutes / 60);
    return `${hours} hour${hours === 1 ? "" : "s"} later`;
  }

  // Different calendar day → always show divider regardless of gap size,
  // because crossing midnight is meaningful even for a 5-minute gap.
  const dayDiff = Math.round(
    (startOfDay(curr) - startOfDay(prev)) / (24 * 60 * 60 * 1000),
  );
  const timeStr = formatTime(curr);

  if (dayDiff === 1) return `Yesterday at ${timeStr}`;
  if (dayDiff <= 7) return `${dayDiff} days ago at ${timeStr}`;

  // Older than a week → absolute date
  return `${MONTH_SHORT[curr.getMonth()]} ${curr.getDate()} at ${timeStr}`;
}
