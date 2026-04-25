"use client";

import * as React from "react";
import { Plus, MessageSquare } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { formatRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

export interface SessionsRailProps {
  sessions: Session[];
  selectedId: string | null;
  loading?: boolean;
  creating?: boolean;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
}

export function SessionsRail({
  sessions,
  selectedId,
  loading,
  creating,
  onSelect,
  onCreate,
}: SessionsRailProps) {
  return (
    <aside
      className={cn(
        "flex w-[240px] shrink-0 flex-col",
        "border-r border-border-subtle bg-surface"
      )}
      aria-label="Agent sessions"
    >
      <header className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
        <span className="t-over fg-muted">Sessions</span>
        <button
          type="button"
          onClick={onCreate}
          disabled={creating}
          className={cn(
            "inline-flex h-6 w-6 items-center justify-center rounded-[5px]",
            "text-fg-tertiary transition-colors duration-fast",
            "hover:bg-hover hover:text-fg-primary disabled:opacity-50"
          )}
          aria-label="New session"
          title="New session"
        >
          {creating ? <Spinner size={11} /> : <Plus size={13} />}
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-1 py-1">
        {loading && sessions.length === 0 ? (
          <SkeletonRows count={5} />
        ) : sessions.length === 0 ? (
          <Empty />
        ) : (
          sessions.map((s) => (
            <SessionRow
              key={s.id}
              session={s}
              active={s.id === selectedId}
              onClick={() => onSelect(s.id)}
            />
          ))
        )}
      </div>
    </aside>
  );
}

function SessionRow({
  session,
  active,
  onClick,
}: {
  session: Session;
  active: boolean;
  onClick: () => void;
}) {
  const title = session.title?.trim() || "(Untitled)";
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative flex w-full flex-col gap-[2px] rounded-[7px] px-2 py-[7px] text-left",
        "transition-colors duration-fast",
        active
          ? "bg-active text-fg-primary"
          : "text-fg-secondary hover:bg-hover hover:text-fg-primary"
      )}
      aria-current={active ? "true" : undefined}
    >
      {active && (
        <span
          className="absolute -left-1 top-2 bottom-2 w-[2px] rounded-[2px] bg-accent"
          aria-hidden
        />
      )}
      <span className="truncate text-[12.5px] font-medium">{title}</span>
      <span className="text-[10.5px] text-fg-muted">
        {formatRelativeTime(session.last_message_at ?? session.created_at)}
      </span>
    </button>
  );
}

function Empty() {
  return (
    <div className="flex flex-col items-center gap-2 px-3 py-10 text-center">
      <MessageSquare size={18} className="text-fg-muted" />
      <div className="text-[12px] text-fg-muted">No sessions yet</div>
    </div>
  );
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <div className="flex flex-col gap-1 px-2 py-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex flex-col gap-1">
          <div className="h-3 w-4/5 animate-shimmer rounded-[4px]" />
          <div className="h-2.5 w-2/5 animate-shimmer rounded-[4px]" />
        </div>
      ))}
    </div>
  );
}
