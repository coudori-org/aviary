import Link from "next/link";
import { ChevronRight, Workflow as WorkflowIcon } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { toneFromId } from "@/lib/tone";
import { formatRelativeTime, formatElapsed } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import type { DashboardRun } from "../hooks/use-dashboard-data";
import type { WorkflowRun } from "@/types";

const COLS =
  "grid grid-cols-[1.4fr_2fr_120px_100px_100px_28px] gap-3 items-center";

export interface RecentRunsCardProps {
  runs: DashboardRun[];
  loading?: boolean;
}

export function RecentRunsCard({ runs, loading }: RecentRunsCardProps) {
  return (
    <section
      className={cn(
        "rounded-[10px] border border-border-subtle bg-raised overflow-hidden"
      )}
    >
      <header className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <h2 className="t-h3 fg-primary">Recent workflow runs</h2>
        <Link
          href={routes.workflows}
          className="text-[11.5px] font-medium text-accent hover:underline"
        >
          All workflows →
        </Link>
      </header>
      <div className="px-4">
        <div
          className={cn(
            COLS,
            "border-b border-border-subtle py-2",
            "t-over fg-muted"
          )}
        >
          <span>Workflow</span>
          <span>Trigger</span>
          <span>Status</span>
          <span>Duration</span>
          <span>When</span>
          <span />
        </div>
        {loading && runs.length === 0 ? (
          <SkeletonRows count={3} />
        ) : runs.length === 0 ? (
          <div className="px-0 py-10 text-center text-[12.5px] text-fg-muted">
            No workflow runs yet.
          </div>
        ) : (
          runs.map(({ run, workflow }, i) => (
            <Link
              key={run.id}
              href={routes.workflow(workflow.id)}
              className={cn(
                COLS,
                "py-2 transition-colors duration-fast",
                "hover:bg-hover -mx-4 px-4",
                i < runs.length - 1 && "border-b border-border-subtle"
              )}
            >
              <div className="flex items-center gap-2 min-w-0">
                <Avatar tone={toneFromId(workflow.id)} size="sm">
                  <WorkflowIcon size={12} />
                </Avatar>
                <span className="truncate text-[13px] font-medium text-fg-primary">
                  {workflow.name}
                </span>
              </div>
              <span className="truncate font-mono text-[12px] text-fg-tertiary">
                {run.trigger_type}
              </span>
              <StatusChip status={run.status} />
              <span className="font-mono text-[12px] text-fg-secondary">
                {formatRunDuration(run)}
              </span>
              <span className="text-[12px] text-fg-tertiary">
                {formatRelativeTime(run.started_at ?? run.created_at)}
              </span>
              <ChevronRight size={13} className="text-fg-muted" />
            </Link>
          ))
        )}
      </div>
    </section>
  );
}

const STATUS_STYLE: Record<
  WorkflowRun["status"],
  { bg: string; fg: string; dot: string; label: string }
> = {
  completed: {
    bg: "bg-status-live-soft",
    fg: "text-status-live",
    dot: "bg-status-live",
    label: "completed",
  },
  running: {
    bg: "bg-status-info-soft",
    fg: "text-status-info",
    dot: "bg-status-info",
    label: "running",
  },
  failed: {
    bg: "bg-status-error-soft",
    fg: "text-status-error",
    dot: "bg-status-error",
    label: "failed",
  },
  pending: {
    bg: "bg-hover",
    fg: "text-fg-tertiary",
    dot: "bg-fg-muted",
    label: "pending",
  },
  cancelled: {
    bg: "bg-hover",
    fg: "text-fg-tertiary",
    dot: "bg-fg-muted",
    label: "cancelled",
  },
};

function StatusChip({ status }: { status: WorkflowRun["status"] }) {
  const s = STATUS_STYLE[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 h-[20px] px-2 rounded-pill w-fit",
        "text-[11px] font-medium",
        s.bg,
        s.fg
      )}
    >
      <span className={cn("inline-block w-[5px] h-[5px] rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

function formatRunDuration(run: WorkflowRun): string {
  if (!run.started_at) return "—";
  const start = new Date(run.started_at).getTime();
  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  const seconds = Math.max(0, (end - start) / 1000);
  return formatElapsed(seconds);
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <div className="flex flex-col">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            COLS,
            "py-3",
            i < count - 1 && "border-b border-border-subtle"
          )}
        >
          <div className="h-3 animate-shimmer rounded-[4px]" />
          <div className="h-3 animate-shimmer rounded-[4px]" />
          <div className="h-5 w-20 animate-shimmer rounded-pill" />
          <div className="h-3 w-16 animate-shimmer rounded-[4px]" />
          <div className="h-3 w-16 animate-shimmer rounded-[4px]" />
          <div />
        </div>
      ))}
    </div>
  );
}
