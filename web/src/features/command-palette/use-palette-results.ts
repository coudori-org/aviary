"use client";

import * as React from "react";
import { agentsApi } from "@/features/agents/api/agents-api";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { searchApi, type MessageSearchHit } from "@/features/search/api/search-api";
import type { Agent, Workflow } from "@/types";

export interface PaletteResults {
  agents: Agent[];
  workflows: Workflow[];
  sessions: MessageSearchHit[];
}

interface State {
  loading: boolean;
  results: PaletteResults;
  error: string | null;
}

const EMPTY_RESULTS: PaletteResults = { agents: [], workflows: [], sessions: [] };

const DEBOUNCE_MS = 180;
const MAX_PER_SECTION = 5;

function fuzzyScore(query: string, target: string): number {
  if (!query) return 0;
  const t = target.toLowerCase();
  const q = query.toLowerCase();
  if (t === q) return 1000;
  if (t.startsWith(q)) return 800;
  const idx = t.indexOf(q);
  if (idx >= 0) return 500 - idx;
  return -1;
}

/**
 * Composite results across agents (server search), workflows (client filter),
 * and sessions (full-text message search). Empty query yields empty results
 * — the palette renders a "Recents" hint instead.
 */
export function usePaletteResults(query: string, enabled: boolean): State {
  const [state, setState] = React.useState<State>({
    loading: false,
    results: EMPTY_RESULTS,
    error: null,
  });
  const reqId = React.useRef(0);

  React.useEffect(() => {
    if (!enabled) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setState({ loading: false, results: EMPTY_RESULTS, error: null });
      return;
    }

    const myReq = ++reqId.current;
    const handle = setTimeout(async () => {
      setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const [agentsRes, workflowsRes, sessionsRes] = await Promise.all([
          agentsApi.list(trimmed).catch(() => ({ items: [], total: 0 })),
          workflowsApi.list().catch(() => ({ items: [], total: 0 })),
          searchApi.searchMessages(trimmed).catch(() => ({ items: [], total: 0 })),
        ]);
        if (myReq !== reqId.current) return;

        const filteredWorkflows = (workflowsRes.items as Workflow[])
          .map((w) => {
            const hay = `${w.name} ${w.slug ?? ""} ${w.description ?? ""}`;
            return { w, score: fuzzyScore(trimmed, hay) };
          })
          .filter((r) => r.score > 0)
          .sort((a, b) => b.score - a.score)
          .slice(0, MAX_PER_SECTION)
          .map((r) => r.w);

        setState({
          loading: false,
          results: {
            agents: (agentsRes.items as Agent[]).slice(0, MAX_PER_SECTION),
            workflows: filteredWorkflows,
            sessions: (sessionsRes.items as MessageSearchHit[]).slice(
              0,
              MAX_PER_SECTION,
            ),
          },
          error: null,
        });
      } catch (e) {
        if (myReq !== reqId.current) return;
        setState({
          loading: false,
          results: EMPTY_RESULTS,
          error: e instanceof Error ? e.message : "Search failed",
        });
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(handle);
  }, [query, enabled]);

  return state;
}
