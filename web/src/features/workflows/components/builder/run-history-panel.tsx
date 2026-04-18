"use client";

import { useCallback, useEffect, useState } from "react";
import { workflowsApi } from "../../api/workflows-api";
import type { WorkflowRun } from "@/types";
import type { useWorkflowRun } from "../../hooks/use-workflow-run";

interface Props {
  workflowId: string;
  run: ReturnType<typeof useWorkflowRun>;
  onOpenRun: () => void;
  /** Always filter by the selection's run_type — draft view lists
   *  only drafts, a deployed-version view lists only deployed runs
   *  (narrowed further by versionId). There's no "show everything"
   *  mode from the inspector anymore. */
  runType: "draft" | "deployed";
  /** When set, narrow deployed runs to this WorkflowVersion. */
  versionId?: string;
}

const STATUS_TONE: Record<string, string> = {
  completed: "text-success",
  failed: "text-danger",
  cancelled: "text-fg-muted",
  running: "text-brand",
  pending: "text-fg-muted",
};

function fmt(ts?: string) {
  return ts ? new Date(ts).toLocaleString() : "—";
}

export function RunHistoryPanel({
  workflowId, run, onOpenRun, runType, versionId,
}: Props) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await workflowsApi.listRuns(workflowId, { runType, versionId });
      setRuns(r.items);
    } finally {
      setLoading(false);
    }
  }, [workflowId, runType, versionId]);

  useEffect(() => { refresh(); }, [refresh]);

  // Auto-refresh when the currently-watched run reaches a terminal state so
  // the listing reflects the latest completion without a manual click.
  useEffect(() => {
    if (["completed", "failed", "cancelled"].includes(run.runStatus)) {
      refresh();
    }
  }, [run.runStatus, refresh]);

  const handleOpen = async (rId: string) => {
    await run.viewRun(rId);
    onOpenRun();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2">
        <span className="type-caption text-fg-muted">Runs</span>
        <button onClick={refresh} className="type-caption text-brand hover:underline">
          {loading ? "…" : "Refresh"}
        </button>
      </div>
      {runs.length === 0 && !loading ? (
        <div className="flex flex-1 items-center justify-center p-4 type-caption text-fg-muted">
          No runs yet
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto divide-y divide-white/[0.04]">
          {runs.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => handleOpen(r.id)}
                className="flex w-full flex-col items-start gap-0.5 px-4 py-2 text-left hover:bg-raised"
              >
                <span className="type-caption flex items-center gap-2">
                  <span className={STATUS_TONE[r.status] ?? "text-fg-muted"}>
                    ● {r.status}
                  </span>
                  <span className="text-fg-muted">{r.run_type}</span>
                  {r.id === run.runId && (
                    <span className="text-brand">(viewing)</span>
                  )}
                </span>
                <span className="type-caption text-fg-muted">{fmt(r.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
