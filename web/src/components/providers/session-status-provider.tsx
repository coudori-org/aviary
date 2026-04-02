"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { apiFetch } from "@/lib/api";

interface SessionStatusEntry {
  status: "streaming" | "idle" | "offline";
  unread: number;
  title: string | null;
}

interface SessionStatusContextValue {
  statuses: Record<string, SessionStatusEntry>;
  sessionIds: string[];
  setSessionIds: (ids: string[]) => void;
}

const SessionStatusContext = createContext<SessionStatusContextValue>({
  statuses: {},
  sessionIds: [],
  setSessionIds: () => {},
});

const POLL_INTERVAL = 5000;

export function SessionStatusProvider({ children }: { children: React.ReactNode }) {
  const [sessionIds, setSessionIds] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<Record<string, SessionStatusEntry>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    if (sessionIds.length === 0) return;

    try {
      const res = await apiFetch<{
        statuses: Record<string, string>;
        unread: Record<string, number>;
        titles: Record<string, string | null>;
      }>(`/sessions/status?ids=${sessionIds.join(",")}`);

      const merged: Record<string, SessionStatusEntry> = {};
      for (const id of sessionIds) {
        merged[id] = {
          status: (res.statuses[id] || "offline") as SessionStatusEntry["status"],
          unread: res.unread[id] || 0,
          title: res.titles[id] ?? null,
        };
      }
      setStatuses(merged);
    } catch {
      // Silently fail — sidebar status is non-critical
    }
  }, [sessionIds]);

  useEffect(() => {
    poll();

    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(poll, POLL_INTERVAL);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [poll]);

  return (
    <SessionStatusContext.Provider value={{ statuses, sessionIds, setSessionIds }}>
      {children}
    </SessionStatusContext.Provider>
  );
}

export function useSessionStatus(sessionId: string): SessionStatusEntry {
  const { statuses } = useContext(SessionStatusContext);
  return statuses[sessionId] || { status: "offline", unread: 0, title: null };
}

export function useSetSessionIds() {
  const { setSessionIds } = useContext(SessionStatusContext);
  return setSessionIds;
}
