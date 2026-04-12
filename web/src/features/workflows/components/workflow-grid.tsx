"use client";

import { WorkflowCard } from "./workflow-card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/empty-state";
import { GitBranch } from "@/components/icons";
import type { Workflow } from "@/types";

interface WorkflowGridProps {
  workflows: Workflow[];
  loading: boolean;
  emptyAction?: React.ReactNode;
  searchActive?: boolean;
}

export function WorkflowGrid({ workflows, loading, emptyAction, searchActive }: WorkflowGridProps) {
  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-44 rounded-lg" />
        ))}
      </div>
    );
  }

  if (workflows.length === 0) {
    return (
      <EmptyState
        icon={<GitBranch size={20} strokeWidth={1.5} />}
        title={searchActive ? "No workflows match your search" : "No workflows yet"}
        description={searchActive ? "Try a different keyword." : "Create your first workflow to get started."}
        action={!searchActive ? emptyAction : undefined}
      />
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
      {workflows.map((w) => (
        <WorkflowCard key={w.id} workflow={w} />
      ))}
    </div>
  );
}
