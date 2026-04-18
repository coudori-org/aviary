import { useCallback, useEffect, useRef } from "react";
import { workflowsApi } from "../api/workflows-api";
import type { WorkflowNode, WorkflowEdge } from "../lib/types";

const DEBOUNCE_MS = 500;

function safeClone(obj: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v === null || v === undefined) { out[k] = v; continue; }
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      out[k] = v;
    } else if (Array.isArray(v)) {
      out[k] = v.map((item) =>
        typeof item === "object" && item !== null ? safeClone(item as Record<string, unknown>) : item,
      );
    } else if (typeof v === "object" && v.constructor === Object) {
      out[k] = safeClone(v as Record<string, unknown>);
    }
    // DOM elements, functions, class instances, and ReactFlow internals (measured, __reactFiber) fall through.
  }
  return out;
}

function stripForSave(nodes: WorkflowNode[], edges: WorkflowEdge[]) {
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: { x: node.position.x, y: node.position.y },
      data: safeClone(node.data as Record<string, unknown>),
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      ...(edge.sourceHandle != null && { sourceHandle: edge.sourceHandle }),
      ...(edge.targetHandle != null && { targetHandle: edge.targetHandle }),
    })),
  };
}

export function useAutoSave(workflowId: string) {
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const scheduleSave = useCallback(
    (nodes: WorkflowNode[], edges: WorkflowEdge[]) => {
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        const clean = stripForSave(nodes, edges);
        workflowsApi.update(workflowId, {
          definition: { ...clean, viewport: { x: 0, y: 0, zoom: 1 } },
        });
      }, DEBOUNCE_MS);
    },
    [workflowId],
  );

  // Flushes a queued save without firing it — needed before cancel-edit so
  // a pending write can't land after the server has already reverted.
  const cancelPendingSave = useCallback(() => {
    clearTimeout(timerRef.current);
    timerRef.current = undefined;
  }, []);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  return { scheduleSave, cancelPendingSave };
}
