"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, RefreshCw } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import type { Workflow, WorkflowRun } from "@/types";

const PAGE_SIZE = 25;

const STATUS_TONE: Record<string, string> = {
  completed: "text-success",
  failed: "text-danger",
  cancelled: "text-fg-muted",
  running: "text-brand",
  pending: "text-fg-muted",
};

const STATUS_DOT: Record<string, string> = {
  completed: "bg-success",
  failed: "bg-danger",
  cancelled: "bg-fg-disabled",
  running: "bg-brand",
  pending: "bg-fg-disabled",
};

function fmt(iso?: string | null) {
  return iso ? new Date(iso).toLocaleString() : "—";
}

function duration(started?: string | null, completed?: string | null) {
  if (!started || !completed) return "—";
  const ms = new Date(completed).getTime() - new Date(started).getTime();
  if (ms < 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  return `${m}m ${s}s`;
}

/**
 * Workflow run history page — full paginated list of deployed runs.
 *
 * The sidebar shows up to 5 recent deployed runs per workflow; this page
 * is the "see all" destination. Drafts are hidden by default (they're
 * test runs, not production activity) but can be toggled in.
 *
 * Clicking a row deep-links to the builder's Test tab with `?runId=`, so
 * the inspector opens on the specific run the user picked.
 */
export default function WorkflowRunsPage() {
  const { user } = useAuth();
  const { id } = useParams<{ id: string }>();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [includeDrafts, setIncludeDrafts] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    workflowsApi.get(id).then(setWorkflow).catch((e: Error) => setError(e.message));
  }, [user, id]);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    workflowsApi
      .listRuns(id, { includeDrafts, offset, limit: PAGE_SIZE })
      .then((data) => {
        setRuns(data.items);
        setTotal(data.total);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [user, id, offset, includeDrafts]);

  if (error) return <ErrorState description={error} />;
  if (!workflow) return <LoadingState />;

  const pageEnd = Math.min(offset + runs.length, total);

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-container px-8 py-8">
        <div className="mb-6">
          <Link
            href={routes.workflow(workflow.id)}
            className="inline-flex items-center gap-1.5 type-caption text-fg-muted hover:text-fg-primary transition-colors"
          >
            <ArrowLeft size={12} strokeWidth={2} />
            {workflow.name}
          </Link>
        </div>

        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <h1 className="type-heading text-fg-primary">Run history</h1>
            <p className="mt-1 type-caption text-fg-muted">
              {total} {includeDrafts ? "total run" : "deployed run"}{total !== 1 ? "s" : ""} for <span className="text-fg-primary">{workflow.name}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 type-caption text-fg-muted cursor-pointer">
              <input
                type="checkbox"
                checked={includeDrafts}
                onChange={(e) => {
                  setIncludeDrafts(e.target.checked);
                  setOffset(0);
                }}
                className="h-3.5 w-3.5"
              />
              Include draft runs
            </label>
            <Button
              variant="ghost"
              onClick={() => {
                setOffset(0);
                // listRuns depends on `offset` — reset above fires the reload.
              }}
              disabled={loading}
            >
              <RefreshCw size={12} strokeWidth={2} className={cn(loading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </div>

        {runs.length === 0 && !loading ? (
          <div className="rounded-md border border-white/[0.06] bg-elevated px-6 py-12 text-center type-caption text-fg-muted">
            {includeDrafts
              ? "No runs yet. Trigger this workflow from the builder to see activity here."
              : "No deployed runs yet. Deploy this workflow and run it to see history."}
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border border-white/[0.06] bg-elevated">
            <div className="divide-y divide-white/[0.04]">
              {runs.map((r) => (
                <Link
                  key={r.id}
                  href={
                    // Include the run's version so the builder opens
                    // the graph at the snapshot that actually ran —
                    // without it the deep-link would overlay node
                    // statuses onto whatever version is latest now.
                    r.version_id
                      ? `${routes.workflow(workflow.id)}?runId=${r.id}&versionId=${r.version_id}`
                      : `${routes.workflow(workflow.id)}?runId=${r.id}&versionId=draft`
                  }
                  className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-4 px-4 py-3 hover:bg-raised/50 transition-colors"
                >
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full",
                      STATUS_DOT[r.status] ?? "bg-fg-disabled",
                    )}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={cn("type-body", STATUS_TONE[r.status] ?? "text-fg-primary")}>
                        {r.status}
                      </span>
                      <Badge variant="info" className="px-1.5">
                        {r.run_type}
                      </Badge>
                      <Badge variant="info" className="px-1.5">
                        {r.trigger_type}
                      </Badge>
                    </div>
                    {r.error && (
                      <p className="mt-0.5 type-caption text-danger truncate">{r.error}</p>
                    )}
                  </div>
                  <span className="type-caption text-fg-muted tabular-nums">
                    {duration(r.started_at, r.completed_at)}
                  </span>
                  <span className="type-caption text-fg-muted tabular-nums">
                    {fmt(r.created_at)}
                  </span>
                </Link>
              ))}
            </div>
            {total > PAGE_SIZE && (
              <div className="flex items-center justify-between border-t border-white/[0.06] px-4 py-2 type-caption text-fg-muted">
                <span>
                  {offset + 1}–{pageEnd} of {total}
                </span>
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    disabled={offset === 0 || loading}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    disabled={pageEnd >= total || loading}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
