"use client";

import { memo, useMemo, useState } from "react";
import { ChevronRight, Check, X, Wrench, Bot } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { formatElapsed } from "@/lib/utils/format";
import { summarizeToolInput } from "./tool-input-summary";
import {
  useChatSearchQuery,
  useChatSearchTargetId,
} from "@/features/chat/hooks/chat-search-context";
import { toolCallMatches } from "@/features/chat/lib/match-block";
import type { StreamBlock, ToolCallBlock } from "@/types";

interface ToolCallCardProps {
  block: ToolCallBlock;
}

/**
 * ToolCallCard — collapsible card for a single tool invocation.
 *
 * Three visual states based on `block.status` + `block.is_error`:
 *   - running: info ring, spinner
 *   - success: subtle border, check icon
 *   - error:   danger ring, X icon
 *
 * Sub-agent tools (Agent, mcp__a2a__ask_*) render their child tools
 * inline as nested cards.
 */
export const ToolCallCard = memo(function ToolCallCard({ block }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const searchQuery = useChatSearchQuery();
  const activeTargetId = useChatSearchTargetId();
  // Auto-expand when search matches anywhere inside this tool.
  const matchesSearch = useMemo(
    () => !!searchQuery && toolCallMatches(block, searchQuery.toLowerCase()),
    [block, searchQuery],
  );
  const effectivelyExpanded = expanded || matchesSearch;
  const isActiveMatch = activeTargetId === block.id;
  const isRunning = block.status === "running";
  const isError = block.is_error === true;
  const summary = summarizeToolInput(block.name, block.input);
  const isSubagent = block.name === "Agent" || block.name.startsWith("mcp__a2a__ask_");
  const a2aSlug = block.name.startsWith("mcp__a2a__ask_")
    ? block.name.replace("mcp__a2a__ask_", "")
    : null;
  const hasChildren = block.children && block.children.length > 0;

  // Jump rail metadata. Status drives the rail tick color:
  //   error → danger, running → info, done → success.
  const railKind = isError ? "tool-error" : isRunning ? "tool-running" : "tool-success";
  const railPreview = `${a2aSlug ? `@${a2aSlug}` : block.name}${summary ? `: ${summary}` : ""}`.slice(0, 100);

  return (
    <div
      data-rail-id={block.id}
      data-rail-kind={railKind}
      data-rail-preview={railPreview}
      data-search-target={block.id}
      className={cn(
        "rounded-md border transition-all",
        isRunning
          ? "border-info/30 bg-info/[0.06]"
          : isError
            ? "border-danger/30 bg-danger/[0.04]"
            : // Default (done) tool cards get a very faint cool-blue tint
              // — enough tone shift to differentiate from the warmer
              // text-bubble surface, but not enough fill to overwhelm
              // the short tool-call content.
              "border-white/[0.06] bg-info/[0.025] hover:bg-info/[0.05]",
        isActiveMatch &&
          "ring-2 ring-info/60 ring-offset-2 ring-offset-canvas",
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left type-caption"
      >
        {/* Status icon */}
        {isRunning ? (
          <Spinner size={13} className="text-info" />
        ) : isError ? (
          <X size={13} strokeWidth={2.5} className="shrink-0 text-danger" />
        ) : (
          <Check size={13} strokeWidth={2.5} className="shrink-0 text-success" />
        )}

        {/* Tool icon */}
        {isSubagent ? (
          <Bot size={13} strokeWidth={1.75} className="shrink-0 text-fg-muted" />
        ) : (
          <Wrench size={13} strokeWidth={1.75} className="shrink-0 text-fg-muted" />
        )}

        <span className="font-mono text-fg-primary">
          {a2aSlug ? `@${a2aSlug}` : block.name}
        </span>

        {summary && <span className="truncate text-fg-muted">{summary}</span>}

        {isSubagent && hasChildren && (
          <span className="rounded-pill bg-info/10 px-1.5 text-[9px] font-medium text-info">
            {block.children!.length} tool{block.children!.length !== 1 ? "s" : ""}
          </span>
        )}

        <span className="flex-1" />

        {block.elapsed != null && (
          <span className="shrink-0 tabular-nums text-fg-disabled">
            {formatElapsed(block.elapsed)}
          </span>
        )}

        <ChevronRight
          size={12}
          strokeWidth={2}
          className={cn(
            "shrink-0 text-fg-disabled transition-transform",
            effectivelyExpanded && "rotate-90",
          )}
        />
      </button>

      {/* Nested sub-agent tools (always visible) */}
      {hasChildren && (
        <div className="border-t border-white/[0.06] px-3 py-2 space-y-1">
          {block.children!.map((child) => (
            <NestedBlock key={child.id} block={child} />
          ))}
        </div>
      )}

      {effectivelyExpanded && (
        <div
          className={cn(
            "border-t border-white/[0.06] px-3 py-2 type-caption",
            hasChildren && "border-t-0 pt-0",
          )}
        >
          <div className="mb-1.5 type-caption-bold text-fg-muted">Input</div>
          {/* Pre blocks revert to bg-canvas so they sit slightly *darker*
              than the info-tinted card, creating an inset look. */}
          <pre className="mb-2 max-h-40 overflow-auto rounded-xs bg-canvas p-2 type-code-sm text-fg-secondary">
            {JSON.stringify(block.input, null, 2)}
          </pre>

          {block.result != null && (
            <>
              <div
                className={cn(
                  "mb-1.5 type-caption-bold",
                  isError ? "text-danger" : "text-fg-muted",
                )}
              >
                {isError ? "Error" : "Result"}
              </div>
              <pre
                className={cn(
                  "max-h-40 overflow-auto rounded-xs p-2 type-code-sm whitespace-pre-wrap",
                  isError
                    ? "bg-danger/[0.06] text-danger"
                    : "bg-canvas text-fg-secondary",
                )}
              >
                {block.result.length > 2000
                  ? block.result.slice(0, 2000) + "\n... (truncated)"
                  : block.result}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  );
});

function NestedBlock({ block }: { block: StreamBlock }) {
  if (block.type === "tool_call") return <ToolCallCard block={block} />;
  return null;
}
