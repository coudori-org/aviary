"use client";

import { memo, useState } from "react";
import { cn } from "@/lib/utils";
import type { TodoItem } from "@/types";

interface TodoPanelProps {
  todos: TodoItem[];
}

function StatusIcon({ status }: { status: TodoItem["status"] }) {
  if (status === "completed") {
    return (
      <svg
        className="h-3 w-3 shrink-0 text-success"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (status === "in_progress") {
    return (
      <svg
        className="h-3 w-3 shrink-0 animate-spin text-primary"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
    );
  }
  return (
    <svg
      className="h-3 w-3 shrink-0 text-muted-foreground/40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
    </svg>
  );
}

export const TodoPanel = memo(function TodoPanel({ todos }: TodoPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (todos.length === 0) return null;

  const completed = todos.filter((t) => t.status === "completed").length;
  const total = todos.length;
  const current = todos.find((t) => t.status === "in_progress");
  const progress = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="relative">
      {/* Expanded list (above the bar) */}
      {expanded && (
        <div className="absolute bottom-full left-0 right-0 mb-1 rounded-lg border border-border/30 bg-background/95 px-3 py-2 shadow-lg backdrop-blur-sm">
          <div className="max-h-48 space-y-0.5 overflow-y-auto">
            {todos.map((todo, i) => (
              <div key={i} className="flex items-start gap-2 py-0.5 text-xs">
                <StatusIcon status={todo.status} />
                <span
                  className={cn(
                    "leading-snug",
                    todo.status === "completed"
                      ? "text-muted-foreground/50 line-through"
                      : todo.status === "in_progress"
                        ? "text-foreground"
                        : "text-muted-foreground/70",
                  )}
                >
                  {todo.content}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Collapsed status bar */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 rounded-lg border border-border/20 bg-secondary/30 px-3 py-1.5 text-xs transition-colors hover:bg-secondary/50"
      >
        {/* Spinner or check */}
        {current ? (
          <svg className="h-3 w-3 shrink-0 animate-spin text-primary" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <svg className="h-3 w-3 shrink-0 text-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}

        {/* Current task or "Done" */}
        <span className="truncate text-foreground/70">
          {current?.content ?? "Plan complete"}
        </span>

        {/* Counter */}
        <span className="shrink-0 text-muted-foreground/50">{completed}/{total}</span>

        {/* Progress bar */}
        <div className="h-1 w-16 shrink-0 rounded-full bg-border/30">
          <div
            className="h-full rounded-full bg-primary/60 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Chevron */}
        <svg
          className={cn(
            "h-3 w-3 shrink-0 text-muted-foreground/40 transition-transform",
            expanded && "rotate-180",
          )}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="18 15 12 9 6 15" />
        </svg>
      </button>
    </div>
  );
});
