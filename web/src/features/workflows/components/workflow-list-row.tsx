"use client";

import Link from "next/link";
import { ChevronRight, Workflow as WorkflowIcon } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { KindBadge, type AssetKind } from "@/components/ui/kind-badge";
import { StatusDot } from "@/components/ui/status-dot";
import { toneFromId } from "@/lib/tone";
import { formatRelativeTime, cn } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import type { Workflow, WorkflowRun } from "@/types";

export const WORKFLOW_LIST_COLS =
  "grid grid-cols-[2fr_2.2fr_110px_70px_70px_120px_28px] gap-3 items-center";

export interface WorkflowListRowProps {
  workflow: Workflow;
  totalRuns?: number;
  lastRun?: WorkflowRun | null;
  kind?: AssetKind;
  divider?: boolean;
}

export function WorkflowListRow({
  workflow,
  totalRuns,
  lastRun,
  kind = "private",
  divider = true,
}: WorkflowListRowProps) {
  const tone = toneFromId(workflow.id);
  const nodeCount = workflow.definition?.nodes?.length ?? 0;
  const statusVariant = lastRun ? runStatusVariant(lastRun.status) : null;
  return (
    <Link
      href={routes.workflow(workflow.id)}
      className={cn(
        WORKFLOW_LIST_COLS,
        "px-4 py-[10px] transition-colors duration-fast hover:bg-hover",
        divider && "border-b border-border-subtle"
      )}
    >
      <div className="flex min-w-0 items-center gap-[10px]">
        <Avatar tone={tone} size="md">
          <WorkflowIcon size={13} />
        </Avatar>
        <span className="truncate text-[13px] font-medium text-fg-primary">
          {workflow.name}
        </span>
      </div>
      <span className="truncate text-[12px] text-fg-tertiary">
        {workflow.description?.trim() || "—"}
      </span>
      <KindBadge kind={kind} />
      <span className="num t-mono text-fg-secondary">{nodeCount}</span>
      <span className="num t-mono text-fg-secondary">{totalRuns ?? 0}</span>
      {statusVariant && lastRun ? (
        <span className="inline-flex items-center gap-1.5 text-[11.5px] text-fg-muted">
          <StatusDot variant={statusVariant} pulse={lastRun.status === "running"} />
          {formatRelativeTime(lastRun.started_at ?? lastRun.created_at)}
        </span>
      ) : (
        <span className="text-[11.5px] text-fg-muted">—</span>
      )}
      <ChevronRight size={14} className="text-fg-muted" />
    </Link>
  );
}

function runStatusVariant(status: WorkflowRun["status"]) {
  switch (status) {
    case "completed":
      return "live" as const;
    case "running":
      return "info" as const;
    case "failed":
      return "error" as const;
    default:
      return "idle" as const;
  }
}
