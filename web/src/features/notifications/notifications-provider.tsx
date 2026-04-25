"use client";

import * as React from "react";

export type NotificationKind =
  | "chat_reply"
  | "workflow_complete"
  | "workflow_failed";

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  title: string;
  description?: string;
  /** ISO timestamp. */
  created_at: string;
  read: boolean;
  /** Where clicking the row should navigate. */
  href?: string;
  /** Stable id used for tone hashing on the avatar. */
  tone_id?: string;
}

interface NotificationsContextValue {
  items: AppNotification[];
  unread: number;
  push: (n: Omit<AppNotification, "id" | "created_at" | "read">) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clear: () => void;
}

const NotificationsContext =
  React.createContext<NotificationsContextValue | null>(null);

const MAX_ITEMS = 50;

/**
 * In-memory feed for terminal events (chat replies, workflow runs). Lives
 * for the session — nothing persists across reloads. Persistence will move
 * to the API later; consumers don't need to know.
 */
export function NotificationsProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<AppNotification[]>([]);

  const push = React.useCallback<NotificationsContextValue["push"]>((n) => {
    setItems((prev) => {
      const next: AppNotification = {
        ...n,
        id: crypto.randomUUID(),
        created_at: new Date().toISOString(),
        read: false,
      };
      return [next, ...prev].slice(0, MAX_ITEMS);
    });
  }, []);

  const markRead = React.useCallback((id: string) => {
    setItems((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n)),
    );
  }, []);

  const markAllRead = React.useCallback(() => {
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const clear = React.useCallback(() => setItems([]), []);

  const unread = React.useMemo(
    () => items.reduce((acc, n) => acc + (n.read ? 0 : 1), 0),
    [items],
  );

  const value = React.useMemo<NotificationsContextValue>(
    () => ({ items, unread, push, markRead, markAllRead, clear }),
    [items, unread, push, markRead, markAllRead, clear],
  );

  return (
    <NotificationsContext.Provider value={value}>
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications(): NotificationsContextValue {
  const ctx = React.useContext(NotificationsContext);
  if (!ctx)
    throw new Error("useNotifications must be used within NotificationsProvider");
  return ctx;
}

/** Read-only variant for components that don't need writers — e.g. the bell
 *  badge in the header. */
export function useNotificationsReadOnly(): {
  unread: number;
  items: AppNotification[];
} {
  const ctx = React.useContext(NotificationsContext);
  if (!ctx) return { unread: 0, items: [] };
  return { unread: ctx.unread, items: ctx.items };
}

/** Push-only optional accessor — returns no-op when no provider is mounted
 *  (e.g. unauthenticated routes). Lets feature hooks emit notifications
 *  without forcing every consumer to be wrapped. */
export function useNotificationsPush(): NotificationsContextValue["push"] {
  const ctx = React.useContext(NotificationsContext);
  return ctx?.push ?? noop;
}

const noop: NotificationsContextValue["push"] = () => {};
