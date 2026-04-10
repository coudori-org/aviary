"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { agentsApi } from "@/features/agents/api/agents-api";
import { extractErrorMessage } from "@/lib/http";
import { routes } from "@/lib/constants/routes";

interface UseCreateSessionResult {
  /** Trigger session creation + navigation. Idempotent while in flight. */
  createAndNavigate: () => Promise<void>;
  /** True from click until either navigation occurs or an error is set. */
  creating: boolean;
  /** Last error message, or null if none / cleared on next click. */
  error: string | null;
}

/**
 * useCreateSession — shared "create new session for agent + navigate" logic.
 *
 * Used by:
 *   - AgentCard's "Start chat" footer button
 *   - AgentDetailHero's primary CTA
 *   - SidebarAgentGroup's hover-revealed "+" button
 *
 * Each call site renders its own UI but the lifecycle (loading state,
 * error surfacing, navigation on success) is identical, so it lives here.
 */
export function useCreateSession(agentId: string): UseCreateSessionResult {
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createAndNavigate = useCallback(async () => {
    if (creating) return;
    setCreating(true);
    setError(null);
    try {
      const session = await agentsApi.createSession(agentId);
      router.push(routes.session(session.id));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      // Always reset — the sidebar consumer survives navigation (AppShell
      // layout stays mounted across routes), so leaving `creating` true
      // would lock the "+" button forever after a successful create.
      // For unmounting consumers (agent card on /agents page) React 18+
      // silently drops the stale setState.
      setCreating(false);
    }
  }, [agentId, creating, router]);

  return { createAndNavigate, creating, error };
}
