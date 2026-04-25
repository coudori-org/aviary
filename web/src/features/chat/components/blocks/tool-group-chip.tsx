"use client";

import { Fragment, memo, useMemo, useState } from "react";
import { ChevronRight } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { ToolCallCard } from "./tool-call-card";
import { cn } from "@/lib/utils";
import { formatElapsed, truncate } from "@/lib/utils/format";
import { useChatSearchQuery } from "@/features/chat/hooks/chat-search-context";
import { toolCallMatches } from "@/features/chat/lib/match-block";
import type { ToolCallBlock } from "@/types";

interface ToolGroupChipProps {
  tools: ToolCallBlock[];
}

/**
 * ToolGroupChip — background-less text-only header for a run of consecutive
 * tool calls. Click to expand → tool cards render as Fragment siblings of
 * the chip, ending up at the SAME visual depth as ungrouped tool calls.
 *
 * Why a chip and not a card: the previous card-style group nested its
 * children inside a bordered container, which collided visually with how
 * sub-agent tool calls render their children inside the parent ToolCallCard.
 * The flat chip + sibling-rendered cards make the grouping a fold-only
 * affordance, not a hierarchy claim.
 *
 * Status is conveyed by text color only:
 *   - hasError → text-danger
 *   - hasRunning → text-info + trailing spinner
 *   - all done → text-fg-muted
 */
export const ToolGroupChip = memo(function ToolGroupChip({ tools }: ToolGroupChipProps) {
  const [expanded, setExpanded] = useState(false);
  const searchQuery = useChatSearchQuery();
  // Auto-expand the group when any child tool matches search.
  const matchesSearch = useMemo(() => {
    if (!searchQuery) return false;
    const lower = searchQuery.toLowerCase();
    return tools.some((t) => toolCallMatches(t, lower));
  }, [tools, searchQuery]);
  const effectivelyExpanded = expanded || matchesSearch;

  const hasRunning = tools.some((t) => t.status === "running");
  const hasError = tools.some((t) => t.is_error === true);
  const lastTool = tools[tools.length - 1];
  const totalElapsed = tools.reduce((sum, t) => sum + (t.elapsed ?? 0), 0);

  return (
    <Fragment>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className={cn(
          "inline-flex max-w-full items-center gap-1.5 rounded-xs px-1 py-0.5 type-caption text-left",
          "transition-colors",
          hasError
            ? "text-danger hover:text-danger"
            : hasRunning
              ? "text-info hover:text-info"
              : "text-fg-muted hover:text-fg-primary",
          "hover:bg-hover",
        )}
      >
        <ChevronRight
          size={11}
          strokeWidth={2}
          className={cn("shrink-0 transition-transform", effectivelyExpanded && "rotate-90")}
        />
        <span className="type-caption-bold">{tools.length} tool calls</span>

        {!expanded && lastTool && (
          <span className="opacity-70">
            · last <span className="font-mono">{truncate(lastTool.name, 30)}</span>
          </span>
        )}

        {totalElapsed > 0 && (
          <span className="opacity-60 tabular-nums shrink-0">
            · {formatElapsed(totalElapsed)}
          </span>
        )}

        {hasRunning && <Spinner size={10} className="ml-1 shrink-0" />}
      </button>

      {/* Expanded tools render as siblings of the chip in the parent flex
          container, so they share the same `space-y-*` rhythm and visual
          depth as ungrouped tool calls. */}
      {effectivelyExpanded &&
        tools.map((tool) => <ToolCallCard key={tool.id} block={tool} />)}
    </Fragment>
  );
});
