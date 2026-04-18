"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { GitBranch } from "@/components/icons";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import type { Workflow } from "@/types";

interface WorkflowCardProps {
  workflow: Workflow;
}

const STATUS_LABELS: Record<Workflow["status"], string> = {
  draft: "Draft",
  deployed: "Deployed",
};

const STATUS_VARIANTS: Record<Workflow["status"], "success" | "muted"> = {
  draft: "muted",
  deployed: "success",
};

export function WorkflowCard({ workflow }: WorkflowCardProps) {
  const nodeCount = workflow.definition?.nodes?.length ?? 0;

  return (
    // Card body goes to the builder (primary interaction), footer has
    // a secondary link to the runs detail page — two separate <Link>s
    // so both targets are reachable without nesting anchors.
    <article
      className={cn(
        "relative flex h-full flex-col rounded-lg p-5 transition-all duration-200",
        "bg-elevated shadow-2 hover:glow-warm",
      )}
    >
      <Link
        href={routes.workflow(workflow.id)}
        className="group flex-1 min-w-0 flex flex-col"
      >
        {/* Header */}
        <div className="mb-3 flex items-start justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-raised">
              <GitBranch size={18} strokeWidth={1.75} className="text-fg-secondary" />
            </div>
            <div className="min-w-0">
              <h3 className="type-body truncate text-fg-primary transition-colors group-hover:text-brand">
                {workflow.name}
              </h3>
              <p className="type-caption text-fg-muted">
                {workflow.model_config?.backend ?? ""} · {nodeCount} node{nodeCount !== 1 ? "s" : ""}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Badge variant={STATUS_VARIANTS[workflow.status]}>
              {STATUS_LABELS[workflow.status]}
              {workflow.status === "deployed" && workflow.current_version != null
                ? ` v${workflow.current_version}`
                : ""}
            </Badge>
          </div>
        </div>

        {/* Description */}
        <p className="mb-4 line-clamp-2 flex-1 type-body-tight text-fg-muted">
          {workflow.description || "No description provided"}
        </p>
      </Link>

      {/* Footer — two actions, separated to keep each Link independently
          navigable (nesting <a> inside <a> is invalid). */}
      <div className="flex items-center justify-between gap-2 border-t border-white/[0.06] pt-3">
        <Link
          href={routes.workflowRuns(workflow.id)}
          className="type-caption text-fg-muted hover:text-fg-primary transition-colors"
        >
          View runs
        </Link>
        <Link
          href={routes.workflow(workflow.id)}
          className="type-caption text-fg-muted hover:text-brand transition-colors"
        >
          Open builder →
        </Link>
      </div>
    </article>
  );
}
