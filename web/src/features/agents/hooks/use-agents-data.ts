"use client";

import { useEffect, useState } from "react";
import { agentsApi } from "@/features/agents/api/agents-api";
import type { Agent } from "@/types";

export interface AgentMeta {
  /** Live count of active sessions for this agent. */
  sessionCount: number;
  /** Combined count of tools (built-in + MCP). */
  toolCount: number;
}

export interface AgentsData {
  agents: Agent[];
  meta: Record<string, AgentMeta>;
  loading: boolean;
  error: string | null;
}

/**
 * Loads the user's agents and per-agent meta (session count + tool count)
 * for the list view. Sessions are fetched lazily after the agents land so
 * the list renders the first paint without waiting on every fan-out.
 */
export function useAgentsData(): AgentsData {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [meta, setMeta] = useState<Record<string, AgentMeta>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await agentsApi.list();
        if (!alive) return;
        const active = res.items.filter((a) => a.status !== "deleted");
        setAgents(active);
        // Seed tool counts immediately; session counts arrive async.
        setMeta(
          Object.fromEntries(
            active.map((a) => [
              a.id,
              {
                toolCount: (a.tools?.length ?? 0) + (a.mcp_servers?.length ?? 0),
                sessionCount: 0,
              },
            ]),
          ),
        );
        // Lazy fan-out for session counts. Failures fall back to 0.
        const counts = await Promise.all(
          active.map((a) =>
            agentsApi
              .listSessions(a.id)
              .then((r) => ({ id: a.id, count: r.items.filter((s) => s.status === "active").length }))
              .catch(() => ({ id: a.id, count: 0 })),
          ),
        );
        if (!alive) return;
        setMeta((prev) => {
          const next = { ...prev };
          for (const c of counts) {
            const cur = next[c.id] ?? { toolCount: 0, sessionCount: 0 };
            next[c.id] = { ...cur, sessionCount: c.count };
          }
          return next;
        });
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return { agents, meta, loading, error };
}
