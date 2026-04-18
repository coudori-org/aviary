"use client";

import { createContext, useContext } from "react";
import type { WorkflowVersionData } from "../api/workflows-api";
import type { Workflow } from "@/types";

export const DRAFT_SELECTION = "draft" as const;

export type SelectedVersion = "draft" | string;

export interface VersionSelection {
  versions: WorkflowVersionData[];
  selected: SelectedVersion;
  isDraft: boolean;
  isLatestVersionSelected: boolean;
  hasPriorDeploy: boolean;
  selectedVersionDefinition: Workflow["definition"] | undefined;
  /** runId from the URL, surfaced only when coherent with `selected`. */
  deepLinkRunId: string | null;
  setSelected: (next: SelectedVersion) => void;
  mutateAndNavigate: (
    next: SelectedVersion | ((latestId: string | null) => SelectedVersion),
  ) => Promise<void>;
}

const VersionSelectionContext = createContext<VersionSelection | null>(null);

export function VersionSelectionProvider({
  value,
  children,
}: {
  value: VersionSelection;
  children: React.ReactNode;
}) {
  return (
    <VersionSelectionContext.Provider value={value}>
      {children}
    </VersionSelectionContext.Provider>
  );
}

export function useVersionSelection() {
  const ctx = useContext(VersionSelectionContext);
  if (!ctx) throw new Error("useVersionSelection must be used within VersionSelectionProvider");
  return ctx;
}
