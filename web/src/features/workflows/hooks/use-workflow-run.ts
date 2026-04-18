import { useCallback, useEffect, useRef, useState } from "react";
import { workflowsApi } from "../api/workflows-api";
import type { WorkflowRun, WorkflowNodeRun } from "@/types";

export type NodeRunStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type RunStatus = "idle" | "pending" | "running" | "completed" | "failed" | "cancelled";

export interface NodeRunData {
  status: NodeRunStatus;
  node_type?: string;
  input_data?: Record<string, unknown> | null;
  output_data?: Record<string, unknown> | null;
  error?: string;
  /** agent_step: the chat session_id the inspector subscribes to. */
  session_id?: string | null;
}

const TERMINAL_RUN_STATUSES: ReadonlySet<RunStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

function nodeRunToState(nr: WorkflowNodeRun): NodeRunData {
  return {
    status: nr.status as NodeRunStatus,
    node_type: nr.node_type,
    input_data: nr.input_data ?? null,
    output_data: nr.output_data ?? null,
    error: nr.error,
    session_id: nr.session_id ?? null,
  };
}

export function useWorkflowRun(workflowId: string) {
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeRunStatus>>({});
  const [nodeData, setNodeData] = useState<Record<string, NodeRunData>>({});
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const reset = useCallback(() => {
    setNodeStatuses({});
    setNodeData({});
    setError(null);
  }, []);

  const applyStaticRun = useCallback((run: WorkflowRun) => {
    // Hydrate state from a completed run's static DB view — no WS involved.
    const statuses: Record<string, NodeRunStatus> = {};
    const data: Record<string, NodeRunData> = {};
    for (const nr of run.node_runs ?? []) {
      statuses[nr.node_id] = nr.status as NodeRunStatus;
      data[nr.node_id] = nodeRunToState(nr);
    }
    setNodeStatuses(statuses);
    setNodeData(data);
    setError(run.error ?? null);
    setRunStatus(run.status as RunStatus);
    setRunId(run.id);
  }, []);

  const connectWs = useCallback((wfId: string, rId: string) => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.hostname}:8000/api/workflows/${wfId}/runs/${rId}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "node_status") {
        setNodeStatuses((prev) => ({ ...prev, [data.node_id]: data.status }));
        setNodeData((prev) => ({
          ...prev,
          [data.node_id]: {
            ...prev[data.node_id],
            status: data.status,
            node_type: data.node_type ?? prev[data.node_id]?.node_type,
            ...(data.input_data !== undefined && { input_data: data.input_data }),
            ...(data.output_data !== undefined && { output_data: data.output_data }),
            ...(data.error && { error: data.error }),
            ...(data.session_id && { session_id: data.session_id }),
          },
        }));
        if (data.error) setError(data.error);
      } else if (data.type === "run_status") {
        setRunStatus(data.status);
        if (data.error) setError(data.error);
        if (TERMINAL_RUN_STATUSES.has(data.status as RunStatus)) {
          ws.close();
        }
      }
    };

    ws.onerror = () => { setError("WebSocket connection failed"); };
    ws.onclose = () => { wsRef.current = null; };
  }, []);

  const trigger = useCallback(async (triggerData?: Record<string, unknown>, runType: "draft" | "deployed" = "draft") => {
    if (runStatus === "running" || runStatus === "pending") return;

    setRunStatus("pending");
    reset();

    try {
      const safe = triggerData && typeof triggerData === "object" && !("nativeEvent" in triggerData)
        ? triggerData : {};
      const run = await workflowsApi.triggerRun(workflowId, { runType, triggerData: safe });
      setRunId(run.id);
      setRunStatus(run.status as RunStatus);
      if (!TERMINAL_RUN_STATUSES.has(run.status as RunStatus)) {
        connectWs(workflowId, run.id);
      }
    } catch (err) {
      setRunStatus("failed");
      setError(err instanceof Error ? err.message : "Failed to start run");
    }
  }, [workflowId, runStatus, connectWs, reset]);

  const viewRun = useCallback(async (rId: string) => {
    // Close any active WS before switching views.
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    reset();
    try {
      const run = await workflowsApi.getRun(workflowId, rId);
      if (TERMINAL_RUN_STATUSES.has(run.status as RunStatus)) {
        applyStaticRun(run);
      } else {
        // Live run — hydrate from the DB snapshot, then tail the WS.
        applyStaticRun(run);
        connectWs(workflowId, rId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run");
    }
  }, [workflowId, reset, applyStaticRun, connectWs]);

  const cancel = useCallback(async () => {
    if (!runId || runStatus !== "running") return;
    try { await workflowsApi.cancelRun(workflowId, runId); } catch { /* best-effort */ }
  }, [workflowId, runId, runStatus]);

  const resume = useCallback(async () => {
    if (!runId || !TERMINAL_RUN_STATUSES.has(runStatus)) return;
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    reset();
    setRunStatus("pending");
    try {
      const newRun = await workflowsApi.resumeRun(workflowId, runId);
      setRunId(newRun.id);
      setRunStatus(newRun.status as RunStatus);
      if (!TERMINAL_RUN_STATUSES.has(newRun.status as RunStatus)) {
        connectWs(workflowId, newRun.id);
      }
    } catch (err) {
      setRunStatus("failed");
      setError(err instanceof Error ? err.message : "Failed to resume");
    }
  }, [workflowId, runId, runStatus, reset, connectWs]);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  return {
    runId, runStatus, nodeStatuses, nodeData, error,
    trigger, viewRun, cancel, resume,
    isRunning: runStatus === "running" || runStatus === "pending",
    canResume: !!runId && TERMINAL_RUN_STATUSES.has(runStatus),
  };
}
