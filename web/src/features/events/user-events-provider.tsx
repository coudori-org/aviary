"use client";

import * as React from "react";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { getWsBaseUrl } from "@/lib/ws/url";

export type UserEvent =
  | {
      type: "session_created";
      session: {
        id: string;
        agent_id: string | null;
        title: string | null;
        status: string;
        created_at: string | null;
        last_message_at: string | null;
      };
    }
  | { type: "session_deleted"; session_id: string }
  | {
      type: "session_changed";
      session_id: string;
      agent_id?: string | null;
      title?: string | null;
      status?: "streaming" | "idle";
      unread?: number;
      terminal?: "done" | "cancelled" | "error";
    };

type Handler = (event: UserEvent) => void;

interface UserEventsContextValue {
  subscribe: (handler: Handler) => () => void;
}

const UserEventsContext = React.createContext<UserEventsContextValue | null>(null);

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000, 10000];

export function UserEventsProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const handlersRef = React.useRef<Set<Handler>>(new Set());

  const subscribe = React.useCallback<UserEventsContextValue["subscribe"]>(
    (handler) => {
      handlersRef.current.add(handler);
      return () => {
        handlersRef.current.delete(handler);
      };
    },
    [],
  );

  React.useEffect(() => {
    if (!user) return;

    let ws: WebSocket | null = null;
    let cancelled = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (cancelled) return;
      const url = `${getWsBaseUrl()}/api/me/events`;
      ws = new WebSocket(url);

      ws.onopen = () => {
        attempt = 0;
      };

      ws.onmessage = (event) => {
        let parsed: UserEvent | null = null;
        try {
          parsed = JSON.parse(event.data) as UserEvent;
        } catch {
          return;
        }
        if (!parsed) return;
        for (const handler of handlersRef.current) handler(parsed);
      };

      ws.onclose = () => {
        if (cancelled) return;
        const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      ws.onerror = () => {};
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        ws.close();
      }
    };
  }, [user]);

  const value = React.useMemo<UserEventsContextValue>(() => ({ subscribe }), [subscribe]);

  return (
    <UserEventsContext.Provider value={value}>{children}</UserEventsContext.Provider>
  );
}

export function useUserEvents(handler: Handler) {
  const ctx = React.useContext(UserEventsContext);
  const ref = React.useRef(handler);
  React.useEffect(() => {
    ref.current = handler;
  }, [handler]);
  React.useEffect(() => {
    if (!ctx) return;
    return ctx.subscribe((event) => ref.current(event));
  }, [ctx]);
}
