"use client";

import * as React from "react";
import Link from "next/link";
import {
  Bell,
  CheckCircle2,
  MessageSquare,
  Workflow as WorkflowIcon,
  XCircle,
} from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { toneFromId } from "@/lib/tone";
import { cn } from "@/lib/utils";
import {
  useNotifications,
  type AppNotification,
  type NotificationKind,
} from "./notifications-provider";

export interface NotificationsPanelProps {
  open: boolean;
  onClose: () => void;
}

export function NotificationsPanel({ open, onClose }: NotificationsPanelProps) {
  const { items, unread, markAllRead, markRead, clear } = useNotifications();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80]" onClick={onClose} role="presentation">
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "absolute right-[14px] top-[52px] w-[360px] overflow-hidden",
          "rounded-[10px] border border-border bg-raised shadow-lg",
          "animate-slide-down",
        )}
        role="dialog"
        aria-label="Notifications"
      >
        <div className="flex items-center justify-between border-b border-border-subtle px-[14px] py-[10px]">
          <div className="flex items-baseline gap-2">
            <span className="t-h3 fg-primary">Notifications</span>
            {unread > 0 && (
              <span className="t-mono text-[11px] text-fg-tertiary tabular-nums">
                {unread} unread
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {unread > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="rounded-[5px] px-2 py-[3px] text-[11px] text-fg-tertiary hover:bg-hover hover:text-fg-primary transition-colors"
              >
                Mark all read
              </button>
            )}
            {items.length > 0 && (
              <button
                type="button"
                onClick={clear}
                className="rounded-[5px] px-2 py-[3px] text-[11px] text-fg-tertiary hover:bg-hover hover:text-fg-primary transition-colors"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {items.length === 0 ? (
          <Empty />
        ) : (
          <ul className="max-h-[480px] overflow-y-auto">
            {items.map((n, i) => (
              <li
                key={n.id}
                className={cn(
                  i < items.length - 1 && "border-b border-border-subtle",
                )}
              >
                <Row
                  notification={n}
                  onClick={() => {
                    markRead(n.id);
                    onClose();
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Row({
  notification,
  onClick,
}: {
  notification: AppNotification;
  onClick: () => void;
}) {
  const tone = toneFromId(notification.tone_id ?? notification.id);
  const Icon = iconFor(notification.kind);
  const iconClass = colorClassFor(notification.kind);
  const body = (
    <div
      className={cn(
        "flex items-start gap-3 px-[14px] py-3",
        "transition-colors duration-fast hover:bg-hover",
      )}
    >
      <Avatar tone={tone} size="md">
        <Icon size={13} className={iconClass} />
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="t-body font-medium fg-primary truncate">
            {notification.title}
          </span>
          {!notification.read && (
            <span
              aria-label="Unread"
              className="ml-auto h-[7px] w-[7px] shrink-0 rounded-full bg-accent"
            />
          )}
        </div>
        {notification.description && (
          <p className="mt-0.5 line-clamp-2 text-[12px] text-fg-tertiary">
            {notification.description}
          </p>
        )}
        <p className="mt-1 text-[10.5px] text-fg-muted">
          {relativeTime(notification.created_at)}
        </p>
      </div>
    </div>
  );
  return notification.href ? (
    <Link href={notification.href} onClick={onClick} className="block">
      {body}
    </Link>
  ) : (
    <button
      type="button"
      onClick={onClick}
      className="block w-full text-left"
    >
      {body}
    </button>
  );
}

function Empty() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-[14px] py-12 text-center text-fg-muted">
      <Bell size={20} className="text-fg-muted" />
      <p className="t-body fg-secondary">You&apos;re all caught up</p>
      <p className="text-[11.5px]">
        Chat replies and workflow run results will appear here.
      </p>
    </div>
  );
}

function iconFor(kind: NotificationKind) {
  if (kind === "chat_reply") return MessageSquare;
  if (kind === "workflow_complete") return CheckCircle2;
  return XCircle;
}

function colorClassFor(kind: NotificationKind): string {
  if (kind === "workflow_complete") return "text-status-live";
  if (kind === "workflow_failed") return "text-status-error";
  return "";
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}
