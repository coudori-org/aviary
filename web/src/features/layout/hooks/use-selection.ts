"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Generic bulk-selection state for list views.
 *
 * - `selected` is the Set of currently selected ids.
 * - `anchor` is the shift-range pivot; updates on plain toggle.
 * - `visibleOrder` is the caller's current rendered order, pushed via
 *   `setVisibleOrder()` from whichever list is mounted. Shift-select
 *   uses this to compute the contiguous span between anchor and click.
 */
export function useSelection() {
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const anchorRef = useRef<string | null>(null);
  const visibleOrderRef = useRef<string[]>([]);

  const setVisibleOrder = useCallback((ids: string[]) => {
    visibleOrderRef.current = ids;
  }, []);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    anchorRef.current = id;
  }, []);

  const shiftSelect = useCallback((id: string) => {
    const ordered = visibleOrderRef.current;
    const anchor = anchorRef.current;
    if (!anchor || !ordered.includes(anchor)) {
      // No usable anchor → plain toggle + set anchor.
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      anchorRef.current = id;
      return;
    }
    const a = ordered.indexOf(anchor);
    const b = ordered.indexOf(id);
    if (b === -1) return;
    const [lo, hi] = a < b ? [a, b] : [b, a];
    const rangeIds = ordered.slice(lo, hi + 1);
    setSelected((prev) => {
      const next = new Set(prev);
      for (const rid of rangeIds) next.add(rid);
      return next;
    });
    // Anchor stays put so subsequent shift-clicks keep extending from it.
  }, []);

  const clear = useCallback(() => {
    setSelected(new Set());
    anchorRef.current = null;
  }, []);

  /** Remove `ids` from the selection without resetting the anchor — useful
   *  after a bulk delete acknowledgement. */
  const remove = useCallback((ids: Iterable<string>) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.delete(id);
      return next;
    });
  }, []);

  return { selected, toggle, shiftSelect, clear, remove, setVisibleOrder };
}
