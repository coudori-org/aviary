"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Play,
  GitBranch,
  Clock,
  CheckCircle2,
  Workflow as WorkflowIcon,
} from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { StatusDot } from "@/components/ui/status-dot";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { WorkflowCrumb } from "@/features/workflows/components/detail/workflow-crumb";
import { useWorkflowDetail } from "@/features/workflows/hooks/use-workflow-detail";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { toneFromId } from "@/lib/tone";
import { formatRelativeTime, formatElapsed, cn } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import type { WorkflowRun } from "@/types";

export default function WorkflowDetailPage() {
  const params = useParams<{ id: string }>();
  const detail = useWorkflowDetail(params.id);

  const crumb = React.useMemo(
    () => (detail.workflow ? <WorkflowCrumb workflow={detail.workflow} trailing="Detail" /> : null),
    [detail.workflow],
  );
  usePageCrumb(crumb);

  const stats = React.useMemo(() => computeStats(detail.runs), [detail.runs]);

  if (detail.loading && !detail.workflow) {
    return <LoadingState fullHeight label="Loading workflow…" />;
  }
  if (detail.error || !detail.workflow) {
    return (
      <ErrorState
        title="Couldn't load workflow"
        description={detail.error ?? "Workflow not found."}
      />
    );
  }

  const wf = detail.workflow;
  const tone = toneFromId(wf.id);
  const nodeCount = wf.definition?.nodes?.length ?? 0;
  const isDeployed = wf.status === "deployed";

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mx-auto max-w-[960px]">
        <header className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <Avatar tone={tone} size="xl">
              <WorkflowIcon size={20} />
            </Avatar>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="t-h1 fg-primary truncate">{wf.name}</h1>
                <StatusBadge deployed={isDeployed} version={wf.current_version ?? null} />
              </div>
              <p className="mt-1 text-[13px] text-fg-secondary">
                {wf.description?.trim() || "No description"}
              </p>
              <div className="mt-2 inline-flex items-center gap-1 t-mono text-[11px] text-fg-tertiary">
                <span>{wf.slug}</span>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href={routes.workflowRuns(wf.id)}>View runs</Link>
            </Button>
            <Button asChild size="sm">
              <Link href={routes.workflow(wf.id)}>Open builder</Link>
            </Button>
          </div>
        </header>

        <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile
            icon={<Play size={14} />}
            label="Total runs"
            value={detail.totalRuns}
          />
          <StatTile
            icon={<CheckCircle2 size={14} />}
            label="Success rate"
            value={stats.successRateLabel}
          />
          <StatTile
            icon={<Clock size={14} />}
            label="Avg duration"
            value={stats.avgDurationLabel}
            mono
          />
          <StatTile
            icon={<GitBranch size={14} />}
            label="Nodes"
            value={nodeCount}
          />
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
          <Section title="Graph snapshot">
            <div className="flex h-[200px] items-center justify-center rounded-[7px] border border-border-subtle bg-sunk text-[12px] text-fg-muted">
              Graph thumbnail coming in Stage B9
            </div>
            <div className="mt-3 flex items-center justify-between text-[11.5px] text-fg-tertiary">
              <span>
                <span className="num t-mono text-fg-secondary">{nodeCount}</span> nodes,{" "}
                <span className="num t-mono text-fg-secondary">
                  {wf.definition?.edges?.length ?? 0}
                </span>{" "}
                edges
              </span>
              <Link
                href={routes.workflow(wf.id)}
                className="text-accent hover:underline"
              >
                Open builder →
              </Link>
            </div>
          </Section>

          <Section title="Recent runs">
            {detail.runs.length === 0 ? (
              <div className="t-small fg-muted">No runs yet.</div>
            ) : (
              <ul className="flex flex-col">
                {detail.runs.slice(0, 6).map((r, i, arr) => (
                  <li key={r.id}>
                    <Link
                      href={routes.workflowRuns(wf.id)}
                      className={cn(
                        "flex items-center justify-between gap-3 px-3 py-[10px]",
                        "transition-colors duration-fast hover:bg-hover",
                        i < arr.length - 1 && "border-b border-border-subtle"
                      )}
                    >
                      <span className="inline-flex min-w-0 items-center gap-2">
                        <StatusDot variant={runStatusVariant(r.status)} pulse={r.status === "running"} />
                        <span className="truncate t-mono text-[12px] text-fg-primary">
                          {r.trigger_type}
                        </span>
                      </span>
                      <span className="shrink-0 text-[11px] text-fg-muted">
                        {formatRelativeTime(r.started_at ?? r.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>

        <Section title="Configuration" className="mt-6">
          <KvRow k="Backend" v={wf.model_config?.backend ?? "—"} />
          <KvRow k="Model" v={wf.model_config?.model ?? "—"} mono />
          <KvRow
            k="Status"
            v={isDeployed ? `Deployed v${wf.current_version ?? 1}` : "Draft"}
          />
          <KvRow k="Updated" v={formatRelativeTime(wf.updated_at)} />
        </Section>
      </div>
    </div>
  );
}

function StatusBadge({ deployed, version }: { deployed: boolean; version: number | null }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 h-[20px] px-2 rounded-pill text-[11px] font-medium",
        deployed
          ? "bg-status-live-soft text-status-live"
          : "bg-hover text-fg-tertiary"
      )}
    >
      <StatusDot variant={deployed ? "live" : "idle"} />
      {deployed ? `Deployed v${version ?? 1}` : "Draft"}
    </span>
  );
}

function StatTile({
  icon,
  label,
  value,
  mono,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-[10px] border border-border-subtle bg-raised p-3">
      <div className="flex items-center gap-1.5 t-small fg-tertiary">
        {icon}
        <span>{label}</span>
      </div>
      <div
        className={cn(
          "num mt-1 truncate text-[18px] font-semibold leading-tight text-fg-primary",
          mono && "t-mono text-[14px] font-medium"
        )}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </div>
    </div>
  );
}

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[10px] border border-border-subtle bg-raised",
        className
      )}
    >
      <header className="border-b border-border-subtle px-3 py-2">
        <h2 className="t-over fg-muted">{title}</h2>
      </header>
      <div className="px-3 py-3">{children}</div>
    </section>
  );
}

function KvRow({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 first:pt-0 last:pb-0">
      <span className="t-small fg-muted">{k}</span>
      <span
        className={cn(
          "truncate text-[12.5px] text-fg-primary",
          mono && "t-mono text-[12px]"
        )}
      >
        {v}
      </span>
    </div>
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

function computeStats(runs: WorkflowRun[]) {
  const completed = runs.filter((r) => r.status === "completed");
  const failed = runs.filter((r) => r.status === "failed");
  const finished = completed.length + failed.length;
  const successRate = finished === 0 ? null : completed.length / finished;
  const successRateLabel =
    successRate == null ? "—" : `${Math.round(successRate * 100)}%`;

  const durations = completed
    .filter((r) => r.started_at && r.completed_at)
    .map(
      (r) =>
        (new Date(r.completed_at as string).getTime() -
          new Date(r.started_at as string).getTime()) /
        1000,
    );
  const avgDurationLabel =
    durations.length === 0
      ? "—"
      : formatElapsed(durations.reduce((s, n) => s + n, 0) / durations.length);

  return { successRateLabel, avgDurationLabel };
}
