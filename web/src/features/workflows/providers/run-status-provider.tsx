"use client";

import { createContext, useContext } from "react";
import type { NodeRunStatus } from "../hooks/use-workflow-run";

const RunStatusContext = createContext<Record<string, NodeRunStatus>>({});

export function RunStatusProvider({
  nodeStatuses,
  children,
}: {
  nodeStatuses: Record<string, NodeRunStatus>;
  children: React.ReactNode;
}) {
  return (
    <RunStatusContext.Provider value={nodeStatuses}>
      {children}
    </RunStatusContext.Provider>
  );
}

export function useNodeRunStatus(nodeId: string): NodeRunStatus | undefined {
  return useContext(RunStatusContext)[nodeId];
}

export function useAllNodeRunStatuses(): Record<string, NodeRunStatus> {
  return useContext(RunStatusContext);
}
