"use client";

import {
  useCallback,
  useLayoutEffect,
  useState,
  type RefObject,
} from "react";
import { cn } from "@/lib/utils";

interface JumpRailProps {
  scrollRef: RefObject<HTMLDivElement | null>;
  /** Drives re-measure on content updates. The actual items are
   *  discovered via `[data-rail-id]` DOM walk. */
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

const MIN_ITEMS = 6;

export function JumpRail({ scrollRef, messageCount }: JumpRailProps) {
  const [items, setItems] = useState<RailItem[]>([]);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

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
      setItems(
        elements.map((el) => ({
          id: el.dataset.railId ?? "",
          kind: (el.dataset.railKind as RailKind) ?? "agent",
          preview: el.dataset.railPreview ?? "",
          top: el.getBoundingClientRect().top - containerTop + scrollTop,
        })),
      );
    };

    measure();
    const inner = scrollEl.firstElementChild;
    if (!inner) return;
    const observer = new ResizeObserver(measure);
    observer.observe(inner);
    return () => observer.disconnect();
  }, [messageCount, scrollRef]);

  const handleJump = useCallback(
    (id: string) => {
      const scrollEl = scrollRef.current;
      if (!scrollEl) return;
      const el = scrollEl.querySelector(
        `[data-rail-id="${CSS.escape(id)}"]`,
      ) as HTMLElement | null;
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    },
    [scrollRef],
  );

  if (items.length < MIN_ITEMS) return null;
  const total = scrollRef.current?.scrollHeight ?? 0;
  if (total <= 0) return null;

  const hovered = hoverIdx !== null ? items[hoverIdx] : null;
  const hoveredPct = hovered ? (hovered.top / total) * 100 : 0;

  return (
    <div
      className="pointer-events-none absolute right-1 top-6 bottom-6 z-10 hidden w-3 lg:block group/rail"
      aria-hidden="true"
    >
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

      {hovered && (
        <div
          className="pointer-events-none absolute right-5 z-20 max-w-[20rem] truncate rounded-md bg-popover px-2 py-1 type-caption text-fg-secondary shadow-lg ring-1 ring-border-subtle"
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

// Legacy `info/success/danger/elevated` palette entries are
// `rgb(var(--legacy-…) / <alpha-value>)`, so they support `/<alpha>`.
// The Slate `var()` tokens (fg-*, accent, status-*) don't.
const kindClasses: Record<RailKind, string> = {
  user: "bg-info/50 group-hover/rail:bg-info/70",
  agent: "bg-elevated/45 group-hover/rail:bg-elevated/75",
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
  agent: "text-fg-secondary",
  "tool-success": "text-success",
  "tool-error": "text-danger",
  "tool-running": "text-info",
};
