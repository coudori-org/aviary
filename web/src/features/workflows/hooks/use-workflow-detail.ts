"use client";

import { useEffect, useState } from "react";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { extractErrorMessage } from "@/lib/http";
import type { Workflow, WorkflowRun } from "@/types";

export interface WorkflowDetailData {
  workflow: Workflow | null;
  runs: WorkflowRun[];
  totalRuns: number;
  loading: boolean;
  error: string | null;
}

const RUN_SAMPLE = 50;

/**
 * Loads a workflow + a sample of recent runs (deployed + draft) used for
 * stat aggregation and the recent-runs strip on the detail page.
 */
export function useWorkflowDetail(workflowId: string): WorkflowDetailData {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [totalRuns, setTotalRuns] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    Promise.all([
      workflowsApi.get(workflowId),
      workflowsApi
        .listRuns(workflowId, { limit: RUN_SAMPLE, includeDrafts: true })
        .catch(() => ({ items: [] as WorkflowRun[], total: 0 })),
    ])
      .then(([w, r]) => {
        if (!alive) return;
        setWorkflow(w);
        setRuns(r.items);
        setTotalRuns(r.total);
      })
      .catch((e) => {
        if (alive) setError(extractErrorMessage(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [workflowId]);

  return { workflow, runs, totalRuns, loading, error };
}
