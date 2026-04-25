"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  useSidebar,
  type SidebarWorkflowGroup,
} from "@/features/layout/providers/sidebar-provider";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { GitBranch } from "@/components/icons";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

const RUN_STATUS_TONE: Record<string, string> = {
  completed: "bg-success",
  failed: "bg-danger",
  cancelled: "bg-fg-disabled",
  running: "bg-brand",
  pending: "bg-fg-disabled",
};

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

function WorkflowGroupRow({ group, currentPath }: {
  group: SidebarWorkflowGroup;
  currentPath: string;
}) {
  const { workflow, runs, totalRuns } = group;
  const builderHref = routes.workflow(workflow.id);
  const runsHref = `${builderHref}/runs`;
  const overflow = Math.max(0, totalRuns - runs.length);

  return (
    <div className="space-y-0.5">
      <Link
        href={builderHref}
        className={cn(
          "flex items-center gap-2 rounded-sm px-3 py-1.5 type-nav transition-colors",
          currentPath === builderHref
            ? "bg-raised text-fg-primary"
            : "text-fg-muted hover:bg-hover hover:text-fg-primary",
        )}
      >
        <GitBranch size={14} strokeWidth={1.75} className="shrink-0 text-fg-disabled" />
        <span className="truncate">{workflow.name}</span>
        {totalRuns > 0 && (
          <Badge variant="info" className="ml-auto px-1.5 shrink-0">
            {totalRuns}
          </Badge>
        )}
      </Link>

      {runs.length > 0 && (
        <ul className="space-y-px pl-5">
          {runs.map((r) => (
            <li key={r.id}>
              <Link
                href={routes.workflowAtVersion(workflow.id, r.version_id ?? "draft", r.id)}
                className="flex items-center gap-2 rounded-sm px-2 py-1 text-fg-muted hover:bg-hover hover:text-fg-primary transition-colors"
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 shrink-0 rounded-full",
                    RUN_STATUS_TONE[r.status] ?? "bg-fg-disabled",
                  )}
                  aria-label={r.status}
                />
                <span className="type-caption truncate">{relativeTime(r.created_at)}</span>
                <span className="type-caption text-fg-disabled truncate">{r.status}</span>
              </Link>
            </li>
          ))}
          <li>
            <Link
              href={runsHref}
              className="block px-2 py-0.5 type-caption text-info hover:underline"
            >
              {overflow > 0 ? `+ ${overflow} more → View all` : "View all runs"}
            </Link>
          </li>
        </ul>
      )}
    </div>
  );
}

export function SidebarWorkflows() {
  const { workflowGroups, loading, collapsed } = useSidebar();
  const pathname = usePathname();

  if (collapsed) return null;

  return (
    <div className="px-3 pt-2">
      <div className="mb-2 flex items-center justify-between px-3">
        <span className="type-small text-fg-disabled">
          Workflows
          {workflowGroups.length > 0 && (
            <Badge variant="info" className="ml-2 px-1.5">
              {workflowGroups.length}
            </Badge>
          )}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2 px-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-6" />
          ))}
        </div>
      ) : workflowGroups.length === 0 ? (
        <p className="px-3 type-caption text-fg-disabled">No workflows yet</p>
      ) : (
        <div className="space-y-2">
          {workflowGroups.map((group) => (
            <WorkflowGroupRow
              key={group.workflow.id}
              group={group}
              currentPath={pathname}
            />
          ))}
        </div>
      )}
    </div>
  );
}
