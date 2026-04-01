"use client";

import { memo, useState } from "react";
import { cn } from "@/lib/utils";
import type { ToolCallBlock } from "@/types";

/** Format elapsed seconds */
function fmtElapsed(s?: number): string {
  if (s == null) return "";
  if (s < 1) return "<1s";
  return `${Math.round(s)}s`;
}

/** Compact summary of tool input */
function inputSummary(name: string, input: Record<string, unknown>): string {
  if (name === "Read" || name === "Write" || name === "Edit") {
    return String(input.description ?? input.file_path ?? input.path ?? "").replace(/^.*\//, "");
  }
  if (name === "Bash") return String(input.description ?? input.command ?? "").slice(0, 60);
  if (name === "Grep" || name === "Glob") return String(input.description ?? input.pattern ?? "").slice(0, 60);
  if (name === "WebFetch") return String(input.description ?? input.url ?? "").slice(0, 60);
  if (name === "Agent") return String(input.description ?? "").slice(0, 60);
  if (name === "TodoWrite") {
    const todos = input.todos as Array<Record<string, string>> | undefined;
    if (todos) return `${todos.length} item${todos.length !== 1 ? "s" : ""}`;
  }
  // Generic: first string value
  const firstVal = Object.values(input).find((v) => typeof v === "string");
  return firstVal ? String(firstVal).slice(0, 60) : "";
}

interface ToolCallCardProps {
  block: ToolCallBlock;
}

export const ToolCallCard = memo(function ToolCallCard({ block }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = block.status === "running";
  const summary = inputSummary(block.name, block.input);
  const isSubagent = block.name === "Agent";

  return (
    <div
      className={cn(
        "rounded-lg border transition-colors",
        isRunning
          ? "border-primary/30 bg-primary/[0.03]"
          : "border-border/30 bg-secondary/30",
      )}
    >
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs"
      >
        {/* Status icon */}
        {isRunning ? (
          <svg
            className="h-3.5 w-3.5 shrink-0 animate-spin text-primary"
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        ) : (
          <svg
            className="h-3.5 w-3.5 shrink-0 text-success"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}

        {/* Tool icon */}
        {isSubagent ? (
          <svg
            className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
        ) : (
          <svg
            className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
          </svg>
        )}

        {/* Name */}
        <span className="font-mono font-medium text-foreground/80">
          {block.name}
        </span>

        {/* Summary */}
        {summary && (
          <span className="truncate text-muted-foreground/60">{summary}</span>
        )}

        {/* Spacer */}
        <span className="flex-1" />

        {/* Elapsed */}
        {block.elapsed != null && (
          <span className="shrink-0 tabular-nums text-muted-foreground/50">
            {fmtElapsed(block.elapsed)}
          </span>
        )}

        {/* Chevron */}
        <svg
          className={cn(
            "h-3 w-3 shrink-0 text-muted-foreground/40 transition-transform",
            expanded && "rotate-90",
          )}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border/20 px-3 py-2 text-xs">
          {/* Input */}
          <div className="mb-1.5 font-medium text-muted-foreground/70">Input</div>
          <pre className="mb-2 max-h-40 overflow-auto rounded bg-[hsl(222_22%_6%)] p-2 text-[11px] leading-relaxed text-muted-foreground">
            {JSON.stringify(block.input, null, 2)}
          </pre>

          {/* Result */}
          {block.result != null && (
            <>
              <div className="mb-1.5 font-medium text-muted-foreground/70">Result</div>
              <pre className="max-h-40 overflow-auto rounded bg-[hsl(222_22%_6%)] p-2 text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap">
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
