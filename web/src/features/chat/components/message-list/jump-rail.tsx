"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";
import { cn } from "@/lib/utils";

interface JumpRailProps {
  /** Ref to the scroll container that holds the messages. The rail
   *  reads positions and dispatches scroll-into-view from this element. */
  scrollRef: RefObject<HTMLDivElement | null>;
  /** Whatever array drives content updates upstream — used only as a
   *  React dependency so the rail re-measures when messages change.
   *  The actual rail items are discovered via DOM query. */
  messageCount: number;
}

type RailKind =
  | "user"
  | "agent"
  | "tool-success"
  | "tool-error"
  | "tool-running";

interface RailItem {
  id: string;
  kind: RailKind;
  preview: string;
  /** Vertical offset (px) from the top of the scroll content. */
  top: number;
}

/** Below this item count the rail provides no value (the user can
 *  see everything in one or two viewports) so we don't render it. */
const MIN_ITEMS = 6;

/**
 * JumpRail — right-side mini-map. Items are discovered by walking
 * `[data-rail-id]` elements inside the scroll container, tagged with
 * `data-rail-kind` and `data-rail-preview`. ResizeObserver re-measures
 * on content reflow.
 */
export function JumpRail({ scrollRef, messageCount }: JumpRailProps) {
  const railRef = useRef<HTMLDivElement>(null);
  const [items, setItems] = useState<RailItem[]>([]);
  // Normalized [0..1] viewport top + height for the indicator band.
  const [viewport, setViewport] = useState({ top: 0, height: 0 });
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  // Drag state lives in a ref so the move handler doesn't re-create on
  // every pointermove (which would also lose pointer capture targeting).
  const dragRef = useRef<{ startY: number; startScrollTop: number } | null>(null);

  // Re-measure whenever messages change or any rendered content reflows
  // (markdown lazy syntax, code-block expansion, tool group expand/collapse).
  useLayoutEffect(() => {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;

    const measure = () => {
      const total = scrollEl.scrollHeight;
      if (total <= 0) return;
      const containerTop = scrollEl.getBoundingClientRect().top;
      const scrollTop = scrollEl.scrollTop;
      const elements = Array.from(
        scrollEl.querySelectorAll<HTMLElement>("[data-rail-id]"),
      );
      const next: RailItem[] = elements.map((el) => ({
        id: el.dataset.railId ?? "",
        kind: (el.dataset.railKind as RailKind) ?? "agent",
        preview: el.dataset.railPreview ?? "",
        top: el.getBoundingClientRect().top - containerTop + scrollTop,
      }));
      setItems(next);
    };

    measure();

    const inner = scrollEl.firstElementChild;
    if (!inner) return;
    const observer = new ResizeObserver(measure);
    observer.observe(inner);
    return () => observer.disconnect();
  }, [messageCount, scrollRef]);

  // Track the current viewport range so the indicator band stays in sync.
  useEffect(() => {
    const scrollEl = scrollRef.current;
    if (!scrollEl) return;
    const update = () => {
      const total = scrollEl.scrollHeight;
      if (total <= 0) return;
      setViewport({
        top: scrollEl.scrollTop / total,
        height: scrollEl.clientHeight / total,
      });
    };
    update();
    scrollEl.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(scrollEl);
    return () => {
      scrollEl.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [scrollRef, messageCount]);

  const handleJump = useCallback(
    (id: string) => {
      const scrollEl = scrollRef.current;
      if (!scrollEl) return;
      const el = scrollEl.querySelector(
        `[data-rail-id="${CSS.escape(id)}"]`,
      ) as HTMLElement | null;
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    },
    [scrollRef],
  );

  // --- Viewport band drag (scrollbar-thumb-like behavior) -------------
  // The band is a draggable handle: 1px of band travel maps to
  // (scrollHeight / railHeight) px of scroll travel, so the band stays
  // glued to the pointer for the entire drag.
  const handleBandPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      const scrollEl = scrollRef.current;
      if (!scrollEl) return;
      e.preventDefault();
      e.stopPropagation();
      dragRef.current = {
        startY: e.clientY,
        startScrollTop: scrollEl.scrollTop,
      };
      setDragging(true);
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [scrollRef],
  );

  const handleBandPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const drag = dragRef.current;
      if (!drag) return;
      const scrollEl = scrollRef.current;
      const railEl = railRef.current;
      if (!scrollEl || !railEl) return;
      const railHeight = railEl.clientHeight;
      if (railHeight <= 0) return;
      const deltaY = e.clientY - drag.startY;
      const scrollDelta = (deltaY / railHeight) * scrollEl.scrollHeight;
      scrollEl.scrollTop = drag.startScrollTop + scrollDelta;
    },
    [scrollRef],
  );

  const handleBandPointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!dragRef.current) return;
      dragRef.current = null;
      setDragging(false);
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    },
    [],
  );

  if (items.length < MIN_ITEMS) return null;
  // If everything fits in the viewport at once, the rail is just clutter.
  if (viewport.height >= 0.99) return null;

  const total = scrollRef.current?.scrollHeight ?? 0;
  if (total <= 0) return null;

  const hovered = hoverIdx !== null ? items[hoverIdx] : null;
  const hoveredPct = hovered ? (hovered.top / total) * 100 : 0;

  return (
    <div
      ref={railRef}
      className="pointer-events-none absolute right-2 top-6 bottom-6 z-10 hidden w-3 lg:block group/rail"
      aria-hidden="true"
    >
      {/* Viewport indicator band — also a draggable handle so the rail
          doubles as a custom scrollbar thumb. Pointer capture keeps the
          drag tracking even if the cursor leaves the rail width. */}
      <div
        onPointerDown={handleBandPointerDown}
        onPointerMove={handleBandPointerMove}
        onPointerUp={handleBandPointerUp}
        onPointerCancel={handleBandPointerUp}
        className={cn(
          "pointer-events-auto absolute inset-x-0 rounded-full transition-colors",
          dragging
            ? "cursor-grabbing bg-fg-disabled/40"
            : "cursor-grab bg-fg-disabled/15 hover:bg-fg-disabled/30 group-hover/rail:bg-fg-disabled/25",
        )}
        style={{
          top: `${viewport.top * 100}%`,
          height: `${Math.max(viewport.height * 100, 4)}%`,
        }}
      />

      {/* Tick marks. Each is a button hit-target wider than the visual
          tick so the rail is forgiving to mouse aim. */}
      {items.map((item, idx) => {
        const pct = (item.top / total) * 100;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => handleJump(item.id)}
            onMouseEnter={() => setHoverIdx(idx)}
            onMouseLeave={() => setHoverIdx((curr) => (curr === idx ? null : curr))}
            aria-label={`Jump to ${item.kind} item`}
            className="pointer-events-auto absolute -left-1 right-0 flex h-2 items-center justify-center"
            style={{ top: `calc(${pct}% - 4px)` }}
          >
            <span
              className={cn(
                "block h-px w-full rounded-full transition-all",
                kindClasses[item.kind],
                hoverIdx === idx && "h-0.5 !bg-fg-primary",
              )}
            />
          </button>
        );
      })}

      {/* Hover preview — single line of the item, anchored to its tick. */}
      {hovered && (
        <div
          className="pointer-events-none absolute right-5 z-20 max-w-[20rem] truncate rounded-md bg-elevated px-2 py-1 type-caption text-fg-secondary shadow-3 ring-1 ring-white/[0.06]"
          style={{
            top: `${hoveredPct}%`,
            transform: "translateY(-50%)",
          }}
        >
          <span className={cn("mr-1.5", kindLabelClasses[hovered.kind])}>
            {kindLabel[hovered.kind]}
          </span>
          {hovered.preview || "(no text)"}
        </div>
      )}
    </div>
  );
}

const kindClasses: Record<RailKind, string> = {
  user: "bg-info/50 group-hover/rail:bg-info/70",
  agent: "bg-fg-disabled/40 group-hover/rail:bg-fg-disabled/70",
  "tool-success": "bg-success/50 group-hover/rail:bg-success/70",
  "tool-error": "bg-danger/60 group-hover/rail:bg-danger/80",
  "tool-running": "bg-info/60 group-hover/rail:bg-info/80",
};

const kindLabel: Record<RailKind, string> = {
  user: "You",
  agent: "AI",
  "tool-success": "Tool",
  "tool-error": "Error",
  "tool-running": "Tool",
};

const kindLabelClasses: Record<RailKind, string> = {
  user: "text-info",
  agent: "text-fg-disabled",
  "tool-success": "text-success",
  "tool-error": "text-danger",
  "tool-running": "text-info",
};
