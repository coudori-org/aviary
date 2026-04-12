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

const VISIBILITY_VARIANTS: Record<Workflow["visibility"], "success" | "warning" | "muted"> = {
  public: "success",
  team: "warning",
  private: "muted",
};

const VISIBILITY_LABELS: Record<Workflow["visibility"], string> = {
  public: "Public",
  team: "Team",
  private: "Private",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  active: "Active",
};

export function WorkflowCard({ workflow }: WorkflowCardProps) {
  const nodeCount = workflow.definition?.nodes?.length ?? 0;

  return (
    <Link href={routes.workflow(workflow.id)} className="group block">
      <article
        className={cn(
          "relative flex h-full flex-col rounded-lg p-5 transition-all duration-200",
          "bg-elevated shadow-2",
          "hover:glow-warm",
        )}
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
            {workflow.status === "draft" && (
              <Badge variant="muted">{STATUS_LABELS[workflow.status]}</Badge>
            )}
            <Badge variant={VISIBILITY_VARIANTS[workflow.visibility]}>
              {VISIBILITY_LABELS[workflow.visibility]}
            </Badge>
          </div>
        </div>

        {/* Description */}
        <p className="mb-4 line-clamp-2 flex-1 type-body-tight text-fg-muted">
          {workflow.description || "No description provided"}
        </p>

        {/* Footer */}
        <div className="flex items-center justify-end border-t border-white/[0.06] pt-3">
          <span className="type-caption text-fg-muted group-hover:text-brand transition-colors">
            Open builder →
          </span>
        </div>
      </article>
    </Link>
  );
}
