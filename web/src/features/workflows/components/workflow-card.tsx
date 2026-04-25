"use client";

import Link from "next/link";
import { GitBranch, Play, Workflow as WorkflowIcon } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { KindBadge, type AssetKind } from "@/components/ui/kind-badge";
import { StatusDot } from "@/components/ui/status-dot";
import { toneFromId } from "@/lib/tone";
import { formatRelativeTime, cn } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import type { Workflow, WorkflowRun } from "@/types";

export interface WorkflowCardProps {
  workflow: Workflow;
  totalRuns?: number;
  lastRun?: WorkflowRun | null;
  kind?: AssetKind;
}

export function WorkflowCard({
  workflow,
  totalRuns,
  lastRun,
  kind = "private",
}: WorkflowCardProps) {
  const tone = toneFromId(workflow.id);
  const nodeCount = workflow.definition?.nodes?.length ?? 0;
  const statusVariant = lastRun ? runStatusVariant(lastRun.status) : null;

  return (
    <Link
      href={routes.workflow(workflow.id)}
      className={cn(
        "group flex flex-col gap-[10px] p-[14px] text-left",
        "rounded-[10px] border border-border-subtle bg-raised",
        "transition-[background,border-color,transform,box-shadow] duration-fast",
        "hover:bg-hover hover:border-border hover:-translate-y-px hover:shadow-md"
      )}
    >
      <header className="flex items-start gap-[10px]">
        <Avatar tone={tone} size="lg">
          <WorkflowIcon size={16} />
        </Avatar>
        <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <div className="flex items-center gap-[6px]">
            <span className="t-h3 fg-primary truncate tracking-[-0.005em]">
              {workflow.name}
            </span>
          </div>
          <div className="flex items-center gap-[6px] text-[11.5px] text-fg-tertiary">
            <KindBadge kind={kind} />
            <span className="t-mono truncate text-[11px]">
              {workflow.status === "deployed"
                ? `v${workflow.current_version ?? 1}`
                : "Draft"}
            </span>
          </div>
        </div>
      </header>

      <p
        className={cn(
          "text-[12.5px] leading-[1.45] text-fg-secondary",
          "min-h-[36px] line-clamp-2"
        )}
      >
        {workflow.description?.trim() || "No description"}
      </p>

      <div className="my-[2px] h-px bg-border-subtle" />

      <footer className="flex items-center gap-3 text-[11.5px] text-fg-tertiary">
        <span className="inline-flex items-center gap-1">
          <GitBranch size={12} />
          <span className="num t-mono">{nodeCount}</span>
          <span className="text-fg-muted">nodes</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <Play size={12} />
          <span className="num t-mono">{totalRuns ?? 0}</span>
          <span className="text-fg-muted">runs</span>
        </span>
        <span className="flex-1" />
        {statusVariant && lastRun ? (
          <span className="inline-flex items-center gap-1.5 text-[11px] text-fg-muted">
            <StatusDot variant={statusVariant} pulse={lastRun.status === "running"} />
            {formatRelativeTime(lastRun.started_at ?? lastRun.created_at)}
          </span>
        ) : (
          <span className="text-[11px] text-fg-muted">No runs</span>
        )}
      </footer>
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
    case "pending":
    case "cancelled":
    default:
      return "idle" as const;
  }
}
