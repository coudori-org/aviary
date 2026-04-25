"use client";

import { useCallback, useEffect, useState } from "react";
import { agentsApi } from "@/features/agents/api/agents-api";
import { extractErrorMessage } from "@/lib/http";
import type { Agent, Session } from "@/types";

export interface AgentDetailData {
  agent: Agent | null;
  sessions: Session[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createSession: () => Promise<Session | null>;
  creating: boolean;
  createError: string | null;
}

/**
 * Loads an agent + its active sessions for the detail page. The chat tab
 * keeps a live sessions list (per-agent), so this hook owns both.
 */
export function useAgentDetail(agentId: string): AgentDetailData {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [a, s] = await Promise.all([
        agentsApi.get(agentId),
        agentsApi.listSessions(agentId).catch(() => ({ items: [] as Session[] })),
      ]);
      setAgent(a);
      setSessions(s.items.filter((x) => x.status === "active"));
    } catch (e) {
      setError(extractErrorMessage(e));
    }
  }, [agentId]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    refresh().finally(() => {
      if (alive) setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [refresh]);

  const createSession = useCallback(async (): Promise<Session | null> => {
    if (creating) return null;
    setCreating(true);
    setCreateError(null);
    try {
      const session = await agentsApi.createSession(agentId);
      setSessions((prev) => [session, ...prev]);
      return session;
    } catch (e) {
      setCreateError(extractErrorMessage(e));
      return null;
    } finally {
      setCreating(false);
    }
  }, [agentId, creating]);

  return {
    agent,
    sessions,
    loading,
    error,
    refresh,
    createSession,
    creating,
    createError,
  };
}
