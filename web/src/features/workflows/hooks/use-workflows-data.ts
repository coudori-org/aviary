"use client";

import { useEffect, useState } from "react";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import type { Workflow, WorkflowRun } from "@/types";

export interface WorkflowMeta {
  /** Total deployed runs (any status). */
  totalRuns: number;
  /** Most recent run, used for status indicator + "last run" timestamp. */
  lastRun: WorkflowRun | null;
}

export interface WorkflowsData {
  workflows: Workflow[];
  meta: Record<string, WorkflowMeta>;
  loading: boolean;
  error: string | null;
}

const RECENT_RUNS_LIMIT = 1;

/**
 * Loads workflows and lazy-fans-out the most recent run + total count per
 * workflow. The first paint shows the catalogue without waiting on every
 * run query.
 */
export function useWorkflowsData(): WorkflowsData {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [meta, setMeta] = useState<Record<string, WorkflowMeta>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await workflowsApi.list();
        if (!alive) return;
        setWorkflows(res.items);
        // Seed empty meta so cards render immediately.
        setMeta(
          Object.fromEntries(
            res.items.map((w) => [w.id, { totalRuns: 0, lastRun: null } as WorkflowMeta]),
          ),
        );

        const counts = await Promise.all(
          res.items.map((w) =>
            workflowsApi
              .listRuns(w.id, { limit: RECENT_RUNS_LIMIT })
              .then((r) => ({ id: w.id, totalRuns: r.total, lastRun: r.items[0] ?? null }))
              .catch(() => ({ id: w.id, totalRuns: 0, lastRun: null })),
          ),
        );
        if (!alive) return;
        setMeta((prev) => {
          const next = { ...prev };
          for (const c of counts) {
            next[c.id] = { totalRuns: c.totalRuns, lastRun: c.lastRun };
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

  return { workflows, meta, loading, error };
}
