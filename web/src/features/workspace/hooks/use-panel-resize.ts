"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UsePanelResizeOptions {
  /** Distinct keys per mode remember different widths (tree-only vs tree+editor). */
  storageKey: string;
  defaultWidth: number;
  minWidth: number;
  /** Reserved viewport width for the main column — panel is clamped to fit.
   *  Omit for inner panels whose ceiling comes from `maxWidth` instead. */
  reserveForMain?: number;
  /** Hard ceiling that overrides the viewport-derived one when smaller.
   *  Used for inner splitters whose room depends on a parent container size. */
  maxWidth?: number;
  /** Which side of the viewport the panel is anchored to. Drag direction
   *  follows: for a left-anchored panel the handle is on its right edge and
   *  pulling rightward grows it; for a right-anchored panel it's the inverse.
   *  Defaults to "right" to keep the workspace panel callsite unchanged. */
  side?: "left" | "right";
}

export function usePanelResize({
  storageKey, defaultWidth, minWidth, reserveForMain, maxWidth, side = "right",
}: UsePanelResizeOptions) {
  const [width, setWidth] = useState(defaultWidth);
  const [isResizing, setIsResizing] = useState(false);
  const draggingRef = useRef(false);
  const widthRef = useRef(defaultWidth);
  // Captured for the mouseup handler so a mode switch mid-drag still
  // persists under the key that was active when the drag started.
  const activeKeyRef = useRef(storageKey);

  const clamp = useCallback((px: number): number => {
    if (typeof window === "undefined") return px;
    const reserve = reserveForMain ?? 0;
    const viewportCeiling = window.innerWidth - reserve;
    const hardCeiling = maxWidth ?? Infinity;
    const ceiling = Math.max(minWidth, Math.min(hardCeiling, viewportCeiling));
    return Math.max(minWidth, Math.min(ceiling, px));
  }, [minWidth, reserveForMain, maxWidth]);

  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  // Load from storage on mount / storageKey change. Intentionally NOT
  // depending on `clamp` so re-clamp triggered by `maxWidth` change doesn't
  // re-read storage every parent-resize frame.
  useEffect(() => {
    activeKeyRef.current = storageKey;
    let next = defaultWidth;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw) {
        const parsed = parseInt(raw, 10);
        if (Number.isFinite(parsed)) next = parsed;
      }
    } catch {
      // Private mode / quota — stay on defaultWidth.
    }
    setWidth(clamp(next));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, defaultWidth]);

  // Re-clamp current width when constraints (viewport / maxWidth) change.
  useEffect(() => {
    setWidth((w) => clamp(w));
  }, [clamp]);

  useEffect(() => {
    const onResize = () => setWidth((w) => clamp(w));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [clamp]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    setIsResizing(true);
    const startX = e.clientX;
    const startWidth = widthRef.current;
    const direction = side === "left" ? 1 : -1;

    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current) return;
      setWidth(clamp(startWidth + (ev.clientX - startX) * direction));
    };
    const onUp = () => {
      draggingRef.current = false;
      setIsResizing(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      try {
        window.localStorage.setItem(activeKeyRef.current, String(widthRef.current));
      } catch {
        // Ignore storage failures.
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [clamp, side]);

  return { width, isResizing, onMouseDown };
}
