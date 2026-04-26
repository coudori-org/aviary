"use client";

import * as React from "react";
import { Plus, MessageSquare, Trash2, Check } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { useSessionStatus } from "@/features/layout/providers/session-status-provider";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { usePanelResize } from "@/features/workspace/hooks/use-panel-resize";
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
  onDelete: (sessionId: string) => Promise<void>;
}

const STORAGE_KEY = "aviary:sessions-rail-width";
const DEFAULT_WIDTH = 240;
const MIN_WIDTH = 200;
const CHAT_MIN_WIDTH = 480;
const NAV_COLLAPSED_WIDTH = 56;
const NAV_EXPANDED_WIDTH = 220;

export function SessionsRail({
  sessions,
  selectedId,
  loading,
  creating,
  onSelect,
  onCreate,
  onDelete,
}: SessionsRailProps) {
  const { collapsed: navCollapsed } = useSidebar();
  const navWidth = navCollapsed ? NAV_COLLAPSED_WIDTH : NAV_EXPANDED_WIDTH;
  const { width, isResizing, onMouseDown } = usePanelResize({
    storageKey: STORAGE_KEY,
    defaultWidth: DEFAULT_WIDTH,
    minWidth: MIN_WIDTH,
    reserveForMain: navWidth + CHAT_MIN_WIDTH,
    side: "left",
  });

  return (
    <aside
      className={cn(
        "relative flex shrink-0 flex-col",
        "border-r border-border-subtle bg-surface",
        !isResizing && "transition-[width] duration-panel ease-panel",
      )}
      style={{ width }}
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
              onDelete={onDelete}
            />
          ))
        )}
      </div>

      <ResizeHandle active={isResizing} onMouseDown={onMouseDown} />
    </aside>
  );
}

function ResizeHandle({
  active,
  onMouseDown,
}: {
  active: boolean;
  onMouseDown: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize sessions panel"
      onMouseDown={onMouseDown}
      className={cn(
        "group absolute top-0 bottom-0 z-20 w-2 translate-x-1/2 cursor-col-resize",
        active && "select-none",
      )}
      style={{ right: 0 }}
    >
      <div
        className={cn(
          "pointer-events-none absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-px transition-colors",
          active
            ? "bg-info/80 w-0.5"
            : "bg-active group-hover:bg-info/60 group-hover:w-0.5",
        )}
      />
    </div>
  );
}

function SessionRow({
  session,
  active,
  onClick,
  onDelete,
}: {
  session: Session;
  active: boolean;
  onClick: () => void;
  onDelete: (sessionId: string) => Promise<void>;
}) {
  const { status, unread, title: liveTitle } = useSessionStatus(session.id);
  const [confirming, setConfirming] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  const isStreaming = status === "streaming";
  const hasUnread = !active && !isStreaming && unread > 0;
  const title = (liveTitle ?? session.title)?.trim() || "(Untitled)";

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setDeleting(true);
    try {
      await onDelete(session.id);
    } catch {
      setDeleting(false);
      setConfirming(false);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      onMouseLeave={() => setConfirming(false)}
      aria-current={active ? "true" : undefined}
      className={cn(
        "group relative flex w-full flex-col gap-[2px] rounded-[7px] px-2 py-[7px] text-left",
        "transition-colors duration-fast cursor-pointer outline-none",
        "focus-visible:ring-1 focus-visible:ring-accent",
        active
          ? "bg-active text-fg-primary"
          : hasUnread
            ? "text-fg-primary hover:bg-hover"
            : "text-fg-secondary hover:bg-hover hover:text-fg-primary",
        deleting && "opacity-50 pointer-events-none",
      )}
    >
      {active && (
        <span
          className="absolute -left-1 top-2 bottom-2 w-[2px] rounded-[2px] bg-accent"
          aria-hidden
        />
      )}

      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            "truncate flex-1 text-[12.5px]",
            (active || hasUnread) ? "font-medium" : "",
            confirming && "text-status-error",
          )}
        >
          {confirming ? "Delete this session?" : title}
        </span>

        {!confirming && isStreaming && (
          <Spinner
            size={11}
            className={cn("shrink-0", active ? "text-info" : "text-info/80")}
          />
        )}

        {!confirming && hasUnread && (
          <span className="flex h-4 min-w-4 shrink-0 items-center justify-center rounded-pill bg-info px-1 text-[9px] font-semibold text-canvas">
            {unread > 99 ? "99+" : unread}
          </span>
        )}

        <button
          type="button"
          onClick={handleDelete}
          tabIndex={-1}
          className={cn(
            "flex h-4 w-4 shrink-0 items-center justify-center rounded transition-colors",
            confirming
              ? "text-status-error"
              : "opacity-0 group-hover:opacity-100 focus:opacity-100 text-fg-muted hover:text-status-error",
          )}
          aria-label={confirming ? "Confirm delete" : "Delete session"}
          title={confirming ? "Click again to confirm" : "Delete session"}
        >
          {confirming ? <Check size={12} strokeWidth={2.5} /> : <Trash2 size={12} strokeWidth={1.75} />}
        </button>
      </div>

      <span className="text-[10.5px] text-fg-muted">
        {formatRelativeTime(session.last_message_at ?? session.created_at)}
      </span>
    </div>
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
