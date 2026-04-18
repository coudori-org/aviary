"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import {
  workflowsApi,
  type WorkflowVersionData,
} from "@/features/workflows/api/workflows-api";
import { WorkflowBuilderProvider } from "@/features/workflows/providers/workflow-builder-provider";
import { WorkflowBuilder } from "@/features/workflows/components/builder/workflow-builder";
import type { Workflow } from "@/types";

/**
 * The version select treats the in-progress editable slot as just
 * another entry in the version list. "draft" is the sentinel for that
 * slot (backed by ``workflow.definition``); any other string is a
 * deployed ``WorkflowVersion.id``. Keeping this a single union means
 * every downstream decision (canvas source, read-only, history filter,
 * trigger gating) keys off one piece of state instead of cross-
 * referencing ``workflow.status``.
 *
 * Kept file-local: Next.js only permits specific named exports from
 * route files, so sharing symbols goes through a module elsewhere.
 */
type SelectedVersion = "draft" | string;

const DRAFT_SELECTION: SelectedVersion = "draft";

export default function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  // Sidebar + runs-detail deep links carry versionId alongside runId —
  // that anchor is what lets the builder open the graph at the snapshot
  // the selected run actually executed against. "draft" is the sentinel
  // for the editable slot (draft runs get it).
  const urlVersionId = searchParams?.get("versionId") ?? null;
  const urlRunId = searchParams?.get("runId") ?? null;
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [versions, setVersions] = useState<WorkflowVersionData[]>([]);
  const [selected, setSelected] = useState<SelectedVersion | null>(null);
  const [error, setError] = useState("");
  // Last URL versionId we synced into state. Guards the URL→state
  // effect so it only fires when the URL actually flips (e.g. sidebar
  // click), not when our own handlers change `selected` internally
  // (Edit / Deploy / Cancel) — otherwise the stale URL would bounce
  // the selection back immediately.
  const lastAppliedUrlVersionIdRef = useRef<string | null>(urlVersionId);

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

  // First load — establish the initial selection from the server's
  // view of the workflow. Draft status implies an active draft slot;
  // otherwise latest deploy is the canonical view. A URL versionId
  // overrides this default (sidebar / runs-page deep link).
  useEffect(() => {
    let cancelled = false;
    loadAll().then((res) => {
      if (cancelled || !res) return;
      if (selected !== null) return; // user already picked something
      if (urlVersionId) {
        setSelected(urlVersionId);
        return;
      }
      if (res.workflow.status === "draft") {
        setSelected(DRAFT_SELECTION);
      } else if (res.versions.length > 0) {
        setSelected(res.versions[0].id);
      } else {
        // Brand-new workflow with no deploys yet — fall back to the
        // draft slot since that's the only thing to show.
        setSelected(DRAFT_SELECTION);
      }
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Subsequent deep-link changes (user clicks another sidebar run
  // while already on this page) update the URL but don't remount. Fire
  // only when the URL itself flips — comparing against the last
  // applied url value, NOT against `selected`. That matters because
  // our own handlers change `selected` while leaving the URL stale
  // for one render; a direct `urlVersionId !== selected` check would
  // wrongly "restore" the stale URL value and undo the handler.
  useEffect(() => {
    if (!urlVersionId) return;
    if (urlVersionId === lastAppliedUrlVersionIdRef.current) return;
    lastAppliedUrlVersionIdRef.current = urlVersionId;
    setSelected(urlVersionId);
  }, [urlVersionId]);

  // After an action that changes server state, refetch and optionally
  // re-point the selection (each handler owns its post-action cursor).
  // Also strips the deep-link query so the stale runId/versionId
  // doesn't outlive the action and trigger URL→state / viewRun
  // effects on the next render.
  const reloadAndSelect = useCallback(
    async (nextSelection: SelectedVersion | ((latestId: string | null) => SelectedVersion)) => {
      const res = await loadAll();
      if (!res) return;
      const resolved = typeof nextSelection === "function"
        ? nextSelection(res.versions[0]?.id ?? null)
        : nextSelection;
      setSelected(resolved);
      lastAppliedUrlVersionIdRef.current = null;
      // Use replace so Back doesn't land on a stale deep-link URL.
      router.replace(`/workflows/${id}`);
    },
    [loadAll, router, id],
  );

  const isDraft = selected === DRAFT_SELECTION;
  const selectedVersion = useMemo(
    () => (!isDraft && selected ? versions.find((v) => v.id === selected) ?? null : null),
    [versions, selected, isDraft],
  );
  const isLatestSelected =
    !isDraft && versions.length > 0 && selected === versions[0].id;

  // Canvas source: draft slot is ``workflow.definition`` (always the
  // freshest editable state); a deployed version is its frozen snapshot.
  const builderWorkflow = useMemo<Workflow | null>(() => {
    if (!workflow) return null;
    if (isDraft) return workflow;
    if (!selectedVersion) return workflow;
    return {
      ...workflow,
      definition: selectedVersion.definition as unknown as Workflow["definition"],
    };
  }, [workflow, isDraft, selectedVersion]);

  // Only surface the URL's runId to the builder when it's coherent
  // with the current selection — i.e. the deep-link versionId matches
  // what we're actually showing. This gates the `viewRun` fire so that
  // an Edit handler's stale URL (one render where `?runId=R&versionId=v1`
  // lingers after setSelected("draft") + router.replace) can't overlay
  // the old run's node statuses onto the freshly-mounted draft view.
  const effectiveDeepLinkRunId =
    urlRunId && urlVersionId === selected ? urlRunId : null;

  if (error) return <ErrorState description={error} />;
  if (!workflow || !builderWorkflow || selected === null) return <LoadingState />;

  return (
    <div className="h-full">
      {/*
        Key on the selection so every switch (Draft ↔ v2 ↔ v1) forces a
        clean WorkflowBuilderProvider remount. The provider seeds its
        nodes/edges + run state on mount only — without a key change
        we'd carry state between versions.
      */}
      <WorkflowBuilderProvider
        key={selected}
        workflow={builderWorkflow}
        isReadOnly={!isDraft}
      >
        <WorkflowBuilder
          versions={versions}
          selected={selected}
          onSelect={setSelected}
          isDraft={isDraft}
          isLatestVersionSelected={isLatestSelected}
          selectedVersionDefinition={
            selectedVersion
              ? (selectedVersion.definition as unknown as Workflow["definition"])
              : undefined
          }
          deepLinkRunId={effectiveDeepLinkRunId}
          reloadAndSelect={reloadAndSelect}
        />
      </WorkflowBuilderProvider>
    </div>
  );
}
