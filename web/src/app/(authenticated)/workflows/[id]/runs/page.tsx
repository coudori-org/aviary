"use client";

import * as React from "react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { RefreshCw, Workflow as WorkflowIcon } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/status-dot";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { WorkflowCrumb } from "@/features/workflows/components/detail/workflow-crumb";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { routes } from "@/lib/constants/routes";
import { toneFromId } from "@/lib/tone";
import { cn } from "@/lib/utils";
import type { Workflow, WorkflowRun } from "@/types";

const PAGE_SIZE = 25;

const STATUS_TONE: Record<string, string> = {
  completed: "text-status-live",
  failed: "text-status-error",
  cancelled: "text-fg-muted",
  running: "text-accent",
  pending: "text-fg-muted",
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

function statusVariant(status: WorkflowRun["status"]) {
  switch (status) {
    case "completed": return "live" as const;
    case "running": return "info" as const;
    case "failed": return "error" as const;
    default: return "idle" as const;
  }
}

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

  const crumb = useMemo(
    () => (workflow ? <WorkflowCrumb workflow={workflow} trailing="Runs" /> : null),
    [workflow],
  );
  usePageCrumb(crumb);

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

  const tone = toneFromId(workflow.id);
  const pageEnd = Math.min(offset + runs.length, total);

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-[1100px] px-8 py-6">
        <header className="flex items-end justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <Avatar tone={tone} size="lg">
              <WorkflowIcon size={16} />
            </Avatar>
            <div className="min-w-0">
              <h1 className="t-h1 fg-primary truncate">Run history</h1>
              <p className="mt-1 text-[12.5px] text-fg-tertiary">
                <span className="num t-mono text-fg-secondary">{total}</span>{" "}
                {includeDrafts ? "total run" : "deployed run"}
                {total !== 1 ? "s" : ""} for{" "}
                <Link
                  href={routes.workflow(workflow.id)}
                  className="text-fg-primary hover:underline decoration-fg-muted underline-offset-2"
                >
                  {workflow.name}
                </Link>
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <label className="inline-flex select-none items-center gap-2 rounded-[7px] bg-hover px-3 py-1.5 text-[12px] text-fg-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={includeDrafts}
                onChange={(e) => {
                  setIncludeDrafts(e.target.checked);
                  setOffset(0);
                }}
                className="h-3.5 w-3.5 accent-accent"
              />
              Include draft runs
            </label>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOffset(0)}
              disabled={loading}
            >
              <RefreshCw size={13} className={cn(loading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </header>

        <div className="mt-6">
          {runs.length === 0 && !loading ? (
            <EmptyState includeDrafts={includeDrafts} />
          ) : (
            <div className="overflow-hidden rounded-[10px] border border-border-subtle bg-raised">
              <div
                className={cn(
                  "grid grid-cols-[auto_1fr_120px_120px_180px] gap-4 items-center",
                  "border-b border-border-subtle px-4 py-[10px] t-over fg-muted"
                )}
              >
                <span />
                <span>Run</span>
                <span>Trigger</span>
                <span>Duration</span>
                <span>Started</span>
              </div>
              <ul className="flex flex-col">
                {runs.map((r, i) => (
                  <li
                    key={r.id}
                    className={cn(i < runs.length - 1 && "border-b border-border-subtle")}
                  >
                    <Link
                      href={routes.workflowAtVersion(workflow.id, r.version_id ?? "draft", r.id)}
                      className={cn(
                        "grid grid-cols-[auto_1fr_120px_120px_180px] items-center gap-4 px-4 py-[10px]",
                        "transition-colors duration-fast hover:bg-hover",
                      )}
                    >
                      <StatusDot variant={statusVariant(r.status)} pulse={r.status === "running"} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={cn("t-body font-medium", STATUS_TONE[r.status] ?? "text-fg-primary")}>
                            {r.status}
                          </span>
                          <Badge variant="default" className="t-mono">
                            {r.run_type}
                          </Badge>
                        </div>
                        {r.error && (
                          <p className="mt-0.5 text-[11.5px] text-status-error truncate">{r.error}</p>
                        )}
                      </div>
                      <span className="t-mono text-[12px] text-fg-secondary truncate">
                        {r.trigger_type}
                      </span>
                      <span className="num t-mono text-[12px] text-fg-secondary tabular-nums">
                        {duration(r.started_at, r.completed_at)}
                      </span>
                      <span className="text-[12px] text-fg-tertiary tabular-nums">
                        {fmt(r.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              {total > PAGE_SIZE && (
                <div className="flex items-center justify-between border-t border-border-subtle px-4 py-2 text-[12px] text-fg-tertiary">
                  <span className="num t-mono">
                    {offset + 1}–{pageEnd} of {total}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                      disabled={offset === 0 || loading}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
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
    </div>
  );
}

function EmptyState({ includeDrafts }: { includeDrafts: boolean }) {
  return (
    <div className="rounded-[10px] border border-border-subtle bg-raised px-6 py-16 text-center text-[12.5px] text-fg-muted">
      {includeDrafts
        ? "No runs yet. Trigger this workflow from the builder to see activity here."
        : "No deployed runs yet. Deploy this workflow and run it to see history."}
    </div>
  );
}
