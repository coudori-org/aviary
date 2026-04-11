"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { http } from "@/lib/http";

type AgentReadiness = "ready" | "offline";

interface AgentStatusContextValue {
  statuses: Record<string, AgentReadiness>;
  setAgentIds: (ids: string[]) => void;
}

const AgentStatusContext = createContext<AgentStatusContextValue | null>(null);

const POLL_INTERVAL = 10_000;

/**
 * Polls /agents/status for the IDs registered via `setAgentIds`.
 *
 * Polling is currently the only mechanism the API exposes for readiness;
 * upgrading to push-based status would happen at this seam without
 * touching consuming components.
 */
export function AgentStatusProvider({ children }: { children: React.ReactNode }) {
  const [agentIds, setAgentIds] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<Record<string, AgentReadiness>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    if (agentIds.length === 0) return;
    try {
      const res = await http.get<{ statuses: Record<string, string> }>(
        `/agents/status?ids=${agentIds.join(",")}`,
      );
      const merged: Record<string, AgentReadiness> = {};
      for (const id of agentIds) {
        merged[id] = res.statuses[id] === "ready" ? "ready" : "offline";
      }
      setStatuses(merged);
    } catch {
      // Status polling failure is non-fatal — sidebar dot just shows "offline".
      // Surfacing toasts here would create constant noise on flaky networks.
    }
  }, [agentIds]);

  useEffect(() => {
    poll();
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(poll, POLL_INTERVAL);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [poll]);

  return (
    <AgentStatusContext.Provider value={{ statuses, setAgentIds }}>
      {children}
    </AgentStatusContext.Provider>
  );
}

function useAgentStatusContext() {
  const ctx = useContext(AgentStatusContext);
  if (!ctx) throw new Error("useAgentStatus must be used within AgentStatusProvider");
  return ctx;
}

export function useAgentStatus(agentId: string): AgentReadiness {
  return useAgentStatusContext().statuses[agentId] || "offline";
}

export function useSetAgentIds() {
  return useAgentStatusContext().setAgentIds;
}
