import { useCallback, useEffect, useRef, useState } from "react";
import { workflowsApi } from "../api/workflows-api";

export type NodeRunStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type RunStatus = "idle" | "pending" | "running" | "completed" | "failed" | "cancelled";

export interface NodeLogEntry {
  node_id: string;
  log_type: string;
  content?: string;
  name?: string;
  input?: Record<string, unknown>;
  timestamp: number;
}

export function useWorkflowRun(workflowId: string) {
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, NodeRunStatus>>({});
  const [logs, setLogs] = useState<NodeLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const connectWs = useCallback((wfId: string, rId: string) => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.hostname}:8000/api/workflows/${wfId}/runs/${rId}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "node_status") {
        setNodeStatuses((prev) => ({ ...prev, [data.node_id]: data.status }));
        if (data.error) {
          setError(data.error);
        }
      } else if (data.type === "node_log") {
        setLogs((prev) => [...prev, { ...data, timestamp: Date.now() }]);
      } else if (data.type === "run_status") {
        setRunStatus(data.status);
        if (data.error) setError(data.error);
        if (["completed", "failed", "cancelled"].includes(data.status)) {
          ws.close();
        }
      }
    };

    ws.onerror = () => {
      setError("WebSocket connection failed");
    };

    ws.onclose = () => {
      wsRef.current = null;
    };
  }, []);

  const trigger = useCallback(async (triggerData?: Record<string, unknown>) => {
    if (runStatus === "running" || runStatus === "pending") return;

    setRunStatus("pending");
    setNodeStatuses({});
    setLogs([]);
    setError(null);

    try {
      const data = triggerData && typeof triggerData === "object" && !("nativeEvent" in triggerData)
        ? triggerData
        : {};
      const run = await workflowsApi.triggerRun(workflowId, data);
      setRunId(run.id);
      setRunStatus("running");
      connectWs(workflowId, run.id);
    } catch (err) {
      setRunStatus("failed");
      setError(err instanceof Error ? err.message : "Failed to start run");
    }
  }, [workflowId, runStatus, connectWs]);

  const cancel = useCallback(async () => {
    if (!runId || runStatus !== "running") return;
    try {
      await workflowsApi.cancelRun(workflowId, runId);
    } catch {
      // Best-effort
    }
  }, [workflowId, runId, runStatus]);

  // Cleanup on unmount
  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  return {
    runId,
    runStatus,
    nodeStatuses,
    logs,
    error,
    trigger,
    cancel,
    isRunning: runStatus === "running" || runStatus === "pending",
  };
}
