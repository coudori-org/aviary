"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UsePanelResizeOptions {
  /** Distinct keys per mode remember different widths (tree-only vs tree+editor). */
  storageKey: string;
  defaultWidth: number;
  minWidth: number;
  maxWidth: number;
  /** Reserved viewport width for the main column — panel is clamped to fit. */
  reserveForMain: number;
}

export function usePanelResize({
  storageKey, defaultWidth, minWidth, maxWidth, reserveForMain,
}: UsePanelResizeOptions) {
  const [width, setWidth] = useState(defaultWidth);
  const [isResizing, setIsResizing] = useState(false);
  const draggingRef = useRef(false);
  // Captured for the mouseup handler so a mode switch mid-drag still
  // persists under the key that was active when the drag started.
  const activeKeyRef = useRef(storageKey);

  const clamp = useCallback((px: number): number => {
    if (typeof window === "undefined") return px;
    const viewportMax = Math.max(minWidth, window.innerWidth - reserveForMain);
    const ceiling = Math.min(maxWidth, viewportMax);
    return Math.max(minWidth, Math.min(ceiling, px));
  }, [minWidth, maxWidth, reserveForMain]);

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
  }, [storageKey, defaultWidth, clamp]);

  useEffect(() => {
    const onResize = () => setWidth((w) => clamp(w));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [clamp]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    setIsResizing(true);

    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current) return;
      setWidth(clamp(window.innerWidth - ev.clientX));
    };
    const onUp = () => {
      draggingRef.current = false;
      setIsResizing(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setWidth((current) => {
        try {
          window.localStorage.setItem(activeKeyRef.current, String(current));
        } catch {
          // Ignore storage failures.
        }
        return current;
      });
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [clamp]);

  return { width, isResizing, onMouseDown };
}
