"use client";

import { memo, useMemo, useState } from "react";
import { ChevronRight } from "@/components/icons";
import {
  useChatSearchQuery,
  useChatSearchTargetId,
} from "@/features/chat/hooks/chat-search-context";
import { cn } from "@/lib/utils";

interface ThinkingChipProps {
  content: string;
  /** Active = currently streaming. Shows trailing bouncing dots when collapsed. */
  isActive?: boolean;
  /** `data-search-target` for in-chat search ring. Omitted during live
   *  streaming where blocks have ephemeral ids. */
  targetId?: string;
}

/**
 * ThinkingChip — background-less text chip for an agent's thinking block.
 *
 * Same flat-chip pattern as ToolGroupChip: chevron + label, click to toggle,
 * expanded content renders as a Fragment sibling so it sits at the same
 * visual depth as the chip rather than nested inside a card.
 *
 * Thinking is treated as low-priority meta information:
 *   - Default collapsed (even during streaming) — peek on demand
 *   - Muted color (`text-fg-disabled`) — no warning yellow
 *   - Indented expanded content (`ml-4`) so it visually attaches to the chip
 *   - Bouncing dots only when actively streaming AND collapsed (otherwise
 *     the streaming text in the expanded view conveys progress)
 */
export const ThinkingChip = memo(function ThinkingChip({
  content,
  isActive = false,
  targetId,
}: ThinkingChipProps) {
  const [expanded, setExpanded] = useState(false);
  const searchQuery = useChatSearchQuery();
  const activeTargetId = useChatSearchTargetId();
  // Auto-expand when search matches inside this thinking block.
  const matchesSearch = useMemo(
    () => !!searchQuery && content.toLowerCase().includes(searchQuery.toLowerCase()),
    [content, searchQuery],
  );
  const effectivelyExpanded = expanded || matchesSearch;
  const isActiveMatch = !!targetId && activeTargetId === targetId;

  return (
    <div
      data-search-target={targetId}
      className={cn(
        "rounded-md transition-shadow",
        isActiveMatch &&
          "ring-2 ring-info/60 ring-offset-2 ring-offset-canvas",
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className={cn(
          "inline-flex max-w-full items-center gap-1.5 rounded-xs px-1 py-0.5 type-caption text-left",
          "text-fg-disabled hover:text-fg-muted hover:bg-hover",
          "transition-colors",
        )}
      >
        <ChevronRight
          size={11}
          strokeWidth={2}
          className={cn("shrink-0 transition-transform", effectivelyExpanded && "rotate-90")}
        />
        <span>Thinking</span>
        {isActive && !effectivelyExpanded && (
          <span className="ml-1 flex items-center gap-1">
            {[0, 150, 300].map((d) => (
              <span
                key={d}
                className="h-1 w-1 animate-bounce rounded-full bg-fg-disabled"
                style={{ animationDelay: `${d}ms`, animationDuration: "0.6s" }}
              />
            ))}
          </span>
        )}
      </button>

      {effectivelyExpanded && (
        <div className="ml-4 type-caption text-fg-disabled whitespace-pre-wrap leading-relaxed">
          {content}
        </div>
      )}
    </div>
  );
});
