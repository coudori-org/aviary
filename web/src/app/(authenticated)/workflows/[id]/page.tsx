"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import {
  workflowsApi,
  type WorkflowVersionData,
} from "@/features/workflows/api/workflows-api";
import { WorkflowBuilderProvider } from "@/features/workflows/providers/workflow-builder-provider";
import {
  VersionSelectionProvider,
  DRAFT_SELECTION,
  type SelectedVersion,
} from "@/features/workflows/providers/version-selection-provider";
import { WorkflowBuilder } from "@/features/workflows/components/builder/workflow-builder";
import { routes } from "@/lib/constants/routes";
import type { Workflow } from "@/types";

export default function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlVersionId = searchParams?.get("versionId") ?? null;
  const urlRunId = searchParams?.get("runId") ?? null;

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [versions, setVersions] = useState<WorkflowVersionData[]>([]);
  const [error, setError] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const [wf, vs] = await Promise.all([
        workflowsApi.get(id),
        workflowsApi.listVersions(id),
      ]);
      setWorkflow(wf);
      setVersions(vs);
      return { workflow: wf, versions: vs };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workflow");
      return null;
    }
  }, [id]);

  // URL is the source of truth for the selected version. On mount, if
  // the URL has no versionId we pick a default (active draft slot, else
  // latest deploy, else draft) and replace-navigate — from then on the
  // URL drives everything.
  useEffect(() => {
    let cancelled = false;
    loadAll().then((res) => {
      if (cancelled || !res) return;
      const current = new URL(window.location.href).searchParams.get("versionId");
      if (current) return;
      const initial: SelectedVersion =
        res.workflow.status === "draft" || res.versions.length === 0
          ? DRAFT_SELECTION
          : res.versions[0].id;
      router.replace(`${routes.workflow(id)}?versionId=${initial}`);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const selected: SelectedVersion = urlVersionId ?? DRAFT_SELECTION;
  const isDraft = selected === DRAFT_SELECTION;
  const selectedVersion = useMemo(
    () => (!isDraft ? versions.find((v) => v.id === selected) ?? null : null),
    [versions, selected, isDraft],
  );
  const isLatestVersionSelected =
    !isDraft && versions.length > 0 && selected === versions[0].id;

  const builderWorkflow = useMemo<Workflow | null>(() => {
    if (!workflow) return null;
    if (isDraft || !selectedVersion) return workflow;
    return {
      ...workflow,
      definition: selectedVersion.definition as unknown as Workflow["definition"],
    };
  }, [workflow, isDraft, selectedVersion]);

  const setSelected = useCallback(
    (next: SelectedVersion) => {
      router.replace(`${routes.workflow(id)}?versionId=${next}`);
    },
    [router, id],
  );

  // After a server-state mutation (Edit / Deploy / Cancel), refetch and
  // navigate to the next selection. Dropping runId on every action keeps
  // a stale deep-link from overlaying an old run's statuses onto the
  // freshly-mounted view.
  const mutateAndNavigate = useCallback(
    async (next: SelectedVersion | ((latestId: string | null) => SelectedVersion)) => {
      const res = await loadAll();
      if (!res) return;
      const resolved = typeof next === "function"
        ? next(res.versions[0]?.id ?? null)
        : next;
      router.replace(`${routes.workflow(id)}?versionId=${resolved}`);
    },
    [loadAll, router, id],
  );

  // Deep-link runId is only valid when the URL explicitly carried a
  // versionId — otherwise `selected` is the default and the runId came
  // from a stale share link.
  const deepLinkRunId = urlVersionId && urlRunId ? urlRunId : null;

  if (error) return <ErrorState description={error} />;
  if (!workflow || !builderWorkflow) return <LoadingState />;

  return (
    <div className="h-full">
      {/* Key on `selected` so every switch (Draft ↔ v2 ↔ v1) forces a
        clean provider remount — otherwise nodes/edges/run state leak
        across versions. */}
      <WorkflowBuilderProvider
        key={selected}
        workflow={builderWorkflow}
        isReadOnly={!isDraft}
      >
        <VersionSelectionProvider
          value={{
            versions,
            selected,
            isDraft,
            isLatestVersionSelected,
            hasPriorDeploy: versions.length > 0,
            selectedVersionDefinition: selectedVersion
              ? (selectedVersion.definition as unknown as Workflow["definition"])
              : undefined,
            deepLinkRunId,
            setSelected,
            mutateAndNavigate,
          }}
        >
          <WorkflowBuilder />
        </VersionSelectionProvider>
      </WorkflowBuilderProvider>
    </div>
  );
}
