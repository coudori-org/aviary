/**
 * Pure formatting helpers — no external deps, no React.
 */

/** Format an absolute date as a short locale string ("Jan 5, 2026"). */
export function formatShortDate(input: string | Date): string {
  const d = typeof input === "string" ? new Date(input) : input;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Compact relative time: "just now" / "5m ago" / "2h ago" / "Yesterday" /
 * "3d ago" / "Jan 5". Falls back to short date past 7 days.
 */
export function formatRelativeTime(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = typeof input === "string" ? new Date(input) : input;
  if (isNaN(d.getTime())) return "";
  const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diffSec < 30) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 86400 * 2) return "Yesterday";
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Format a number with thousands separators. */
export function formatCount(n: number): string {
  return n.toLocaleString();
}

/** Format token count as "Nk" (e.g., 4000 → "4k"). */
export function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(0)}k`;
}

/** Format elapsed seconds as "<1s", "5s", "1m 23s". */
export function formatElapsed(seconds?: number): string {
  if (seconds == null) return "";
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

/** Truncate a string with ellipsis if it exceeds max length. */
export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 1) + "…";
}

/** Generate a URL-safe slug from a name. */
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
