"use client";

import { memo, useState } from "react";
import { ChevronUp, Check, Circle } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { TodoItem } from "@/types";

interface TodoPanelProps {
  todos: TodoItem[];
}

function StatusIcon({ status }: { status: TodoItem["status"] }) {
  if (status === "completed") return <Check size={11} strokeWidth={2.5} className="shrink-0 text-success" />;
  if (status === "in_progress") return <Spinner size={11} className="shrink-0 text-info" />;
  return <Circle size={11} strokeWidth={2} className="shrink-0 text-fg-disabled" />;
}

/**
 * TodoPanel — shows the agent's current task list (from TodoWrite tool).
 * Collapsed by default; clicking the bar expands the full list above.
 */
export const TodoPanel = memo(function TodoPanel({ todos }: TodoPanelProps) {
  const [expanded, setExpanded] = useState(false);

  if (todos.length === 0) return null;

  const completed = todos.filter((t) => t.status === "completed").length;
  const total = todos.length;
  const inProgress = todos.filter((t) => t.status === "in_progress");
  const progress = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="relative">
      {expanded && (
        <div className="absolute bottom-full left-0 right-0 mb-1 rounded-md bg-popover border border-border shadow-5 px-3 py-2">
          <div className="max-h-48 space-y-0.5 overflow-y-auto">
            {todos.map((todo, i) => (
              <div key={i} className="flex items-start gap-2 py-0.5 type-caption">
                <StatusIcon status={todo.status} />
                <span
                  className={cn(
                    "leading-snug",
                    todo.status === "completed" && "text-fg-disabled line-through",
                    todo.status === "in_progress" && "text-fg-primary",
                    todo.status === "pending" && "text-fg-muted",
                  )}
                >
                  {todo.content}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 rounded-md bg-elevated border border-border-subtle px-3 py-1.5 type-caption transition-colors hover:bg-raised"
      >
        {inProgress.length > 0 ? (
          <Spinner size={11} className="shrink-0 text-info" />
        ) : (
          <Check size={11} strokeWidth={2.5} className="shrink-0 text-success" />
        )}

        <span className="min-w-0 truncate text-fg-secondary">
          {inProgress.length === 0
            ? "Plan complete"
            : inProgress.map((t) => t.content).join(" · ")}
        </span>

        <span className="shrink-0 text-fg-disabled">
          {completed}/{total}
        </span>

        <div className="h-1 w-16 shrink-0 rounded-pill bg-hover">
          <div
            className="h-full rounded-pill bg-info/60 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        <ChevronUp
          size={11}
          strokeWidth={2}
          className={cn(
            "shrink-0 text-fg-disabled transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>
    </div>
  );
});
