"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { http } from "@/lib/http";

interface SessionStatusEntry {
  status: "streaming" | "idle" | "offline";
  unread: number;
  title: string | null;
}

interface SessionStatusContextValue {
  statuses: Record<string, SessionStatusEntry>;
  setSessionIds: (ids: string[]) => void;
}

const SessionStatusContext = createContext<SessionStatusContextValue | null>(null);

const POLL_INTERVAL = 5_000;

const DEFAULT_ENTRY: SessionStatusEntry = { status: "offline", unread: 0, title: null };

export function SessionStatusProvider({ children }: { children: React.ReactNode }) {
  const [sessionIds, setSessionIds] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<Record<string, SessionStatusEntry>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    if (sessionIds.length === 0) return;
    try {
      const res = await http.get<{
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
      // Same rationale as agent status: non-fatal sidebar polling.
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
    <SessionStatusContext.Provider value={{ statuses, setSessionIds }}>
      {children}
    </SessionStatusContext.Provider>
  );
}

function useSessionStatusContext() {
  const ctx = useContext(SessionStatusContext);
  if (!ctx) throw new Error("useSessionStatus must be used within SessionStatusProvider");
  return ctx;
}

export function useSessionStatus(sessionId: string): SessionStatusEntry {
  return useSessionStatusContext().statuses[sessionId] || DEFAULT_ENTRY;
}

export function useSetSessionIds() {
  return useSessionStatusContext().setSessionIds;
}
