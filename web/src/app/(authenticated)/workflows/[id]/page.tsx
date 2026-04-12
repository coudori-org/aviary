"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { WorkflowBuilderProvider } from "@/features/workflows/providers/workflow-builder-provider";
import { WorkflowBuilder } from "@/features/workflows/components/builder/workflow-builder";
import type { Workflow } from "@/types";

export default function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [error, setError] = useState("");

  const loadWorkflow = useCallback(() => {
    workflowsApi
      .get(id)
      .then(setWorkflow)
      .catch((err) => setError(err.message || "Failed to load workflow"));
  }, [id]);

  useEffect(() => { loadWorkflow(); }, [loadWorkflow]);

  const handleStatusChange = useCallback(() => {
    loadWorkflow();
  }, [loadWorkflow]);

  if (error) return <ErrorState description={error} />;
  if (!workflow) return <LoadingState />;

  return (
    <div className="h-full">
      <WorkflowBuilderProvider workflow={workflow}>
        <WorkflowBuilder onStatusChange={handleStatusChange} />
      </WorkflowBuilderProvider>
    </div>
  );
}
