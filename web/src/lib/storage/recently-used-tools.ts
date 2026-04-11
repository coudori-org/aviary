/**
 * Recently-used MCP tool ids, persisted to localStorage so the tool
 * picker can surface them at the top of the left rail across sessions.
 *
 * Ordered most-recent first. Capped at MAX_ITEMS so the list never
 * grows unbounded. Tools remain in the list even after they're removed
 * from an agent — "recent" tracks user attention, not current usage.
 */

const STORAGE_KEY = "aviary_recent_tool_ids";
const MAX_ITEMS = 10;

export function loadRecentToolIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === "string").slice(0, MAX_ITEMS);
  } catch {
    return [];
  }
}

/** Push a tool id to the front of the recent list. Deduplicates by
 *  removing any existing entry first so the most recent use wins. */
export function pushRecentToolId(toolId: string): string[] {
  if (typeof window === "undefined") return [];
  const current = loadRecentToolIds();
  const next = [toolId, ...current.filter((id) => id !== toolId)].slice(0, MAX_ITEMS);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage quota / disabled — silently skip; list just won't persist.
  }
  return next;
}
