"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import type { Workflow } from "@/types";

export default function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    workflowsApi
      .get(id)
      .then(setWorkflow)
      .catch((err) => setError(err.message || "Failed to load workflow"));
  }, [id]);

  if (error) return <ErrorState description={error} />;
  if (!workflow) return <LoadingState />;

  return (
    <div className="flex h-full flex-col bg-canvas">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <h1 className="type-body text-fg-primary">{workflow.name}</h1>
        <span className="type-caption text-fg-muted">Builder — coming next step</span>
      </div>
      <div className="flex-1 flex items-center justify-center text-fg-muted type-body">
        React Flow canvas will be implemented in the next task.
      </div>
    </div>
  );
}
