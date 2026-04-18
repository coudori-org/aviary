"use client";

import { createContext, useContext, useCallback, useEffect, useRef, useState } from "react";
import {
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type OnNodesChange,
  type OnEdgesChange,
} from "@xyflow/react";
import { useWorkflowHistory } from "../hooks/use-workflow-history";
import { workflowsApi } from "../api/workflows-api";
import type { Workflow } from "@/types";
import type { WorkflowNode, WorkflowEdge, NodeType, NodeData } from "../lib/types";
import { NODE_REGISTRY } from "../lib/node-registry";
import { applyPlan as applyPlanPure, validatePlan, type PlanOp } from "../lib/assistant-plan";

interface WorkflowBuilderContextValue {
  workflowId: string;
  workflowName: string;
  /** True when the current view is a deployed version snapshot — the
   *  inspector + keyboard shortcuts switch to read-only. The page owns
   *  the selection that drives this and passes it in at provider
   *  construction time. */
  isReadOnly: boolean;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  onNodesChange: OnNodesChange<WorkflowNode>;
  onEdgesChange: OnEdgesChange<WorkflowEdge>;
  onNodeDragStart: () => void;
  onNodeDragStop: () => void;
  onConnect: (connection: Connection) => void;
  addNode: (type: NodeType, position: { x: number; y: number }) => void;
  updateNodeData: (nodeId: string, key: string, value: unknown) => void;
  deleteSelected: () => void;
  applyPlan: (plan: PlanOp[]) => { ok: boolean; error?: string };
  workflowModelBackend: string;
  workflowModelName: string;
  selectedNodeId: string | null;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  /** Cancel the pending debounced auto-save without firing it. Used
   *  before cancel-edit so a save that was queued right before the
   *  click can't overwrite the server's reverted definition. */
  cancelPendingSave: () => void;
}

const WorkflowBuilderContext = createContext<WorkflowBuilderContextValue | null>(null);

export function useWorkflowBuilder() {
  const ctx = useContext(WorkflowBuilderContext);
  if (!ctx) throw new Error("useWorkflowBuilder must be used within WorkflowBuilderProvider");
  return ctx;
}

interface Props {
  workflow: Workflow;
  /** Whether the current view is a read-only snapshot. Controls whether
   *  the inspector + keyboard shortcuts accept edits. The canvas
   *  separately reads ``isReadOnly`` via its own prop so ReactFlow's
   *  interaction flags can be bound at the right level. */
  isReadOnly?: boolean;
  children: React.ReactNode;
}

export function WorkflowBuilderProvider({ workflow, isReadOnly = false, children }: Props) {
  const initialNodes = (workflow.definition?.nodes ?? []) as WorkflowNode[];
  const initialEdges = (workflow.definition?.edges ?? []) as WorkflowEdge[];

  const [nodes, setNodes, onNodesChangeBase] = useNodesState<WorkflowNode>(initialNodes);
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<WorkflowEdge>(initialEdges);
  const history = useWorkflowHistory();
  // Force re-render for canUndo/canRedo button states
  const [, bump] = useState(0);
  const forceBump = () => bump((n) => n + 1);

  const selectedNodeId = nodes.find((n) => n.selected)?.id ?? null;

  // --- Auto-save ---
  // Deep-strip React Flow internals (measured, internals, __reactFiber, etc.)
  // to produce a plain JSON-safe object for backend persistence.
  const safeClone = (obj: Record<string, unknown>): Record<string, unknown> => {
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
      // Skip DOM elements, functions, class instances, etc.
    }
    return out;
  };

  const stripForSave = (n: WorkflowNode[], e: WorkflowEdge[]) => ({
    nodes: n.map((node) => ({
      id: node.id,
      type: node.type,
      position: { x: node.position.x, y: node.position.y },
      data: safeClone(node.data as Record<string, unknown>),
    })),
    edges: e.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      ...(edge.sourceHandle != null && { sourceHandle: edge.sourceHandle }),
      ...(edge.targetHandle != null && { targetHandle: edge.targetHandle }),
    })),
  });

  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const scheduleSave = useCallback(
    (n: WorkflowNode[], e: WorkflowEdge[]) => {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        const clean = stripForSave(n, e);
        workflowsApi.update(workflow.id, {
          definition: { ...clean, viewport: { x: 0, y: 0, zoom: 1 } },
        });
      }, 500);
    },
    [workflow.id],
  );

  const cancelPendingSave = useCallback(() => {
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = undefined;
  }, []);

  // Drop any pending save on unmount — the builder page remounts the
  // provider on version switch / status flip, and a leftover timer
  // from the prior instance would fire against the old state.
  useEffect(() => {
    return () => clearTimeout(saveTimerRef.current);
  }, []);

  // Push current state to history, then apply new state
  const commit = useCallback(
    (nextNodes: WorkflowNode[], nextEdges: WorkflowEdge[]) => {
      // Save current state as history entry BEFORE applying new state
      history.push({ nodes, edges });
      setNodes(nextNodes);
      setEdges(nextEdges);
      scheduleSave(nextNodes, nextEdges);
      forceBump();
    },
    [history, nodes, edges, setNodes, setEdges, scheduleSave],
  );

  // --- React Flow handlers (no history, just state) ---
  const onNodesChange: OnNodesChange<WorkflowNode> = onNodesChangeBase;
  const onEdgesChange: OnEdgesChange<WorkflowEdge> = onEdgesChangeBase;

  // Capture pre-drag snapshot on drag start, push it on drag stop
  const preDragRef = useRef<{ nodes: WorkflowNode[]; edges: WorkflowEdge[] } | null>(null);

  const onNodeDragStart = useCallback(() => {
    preDragRef.current = { nodes, edges };
  }, [nodes, edges]);

  const onNodeDragStop = useCallback(() => {
    if (preDragRef.current) {
      // Only push to history if positions actually changed
      const pre = preDragRef.current.nodes;
      const moved = nodes.some((n) => {
        const old = pre.find((p) => p.id === n.id);
        return old && (old.position.x !== n.position.x || old.position.y !== n.position.y);
      });
      if (moved) {
        history.push(preDragRef.current);
        scheduleSave(nodes, edges);
        forceBump();
      }
      preDragRef.current = null;
    }
  }, [history, nodes, edges, scheduleSave]);

  // --- Undo / Redo ---
  const undo = useCallback(() => {
    history.undo({ nodes, edges }, (snapshot) => {
      setNodes(snapshot.nodes as WorkflowNode[]);
      setEdges(snapshot.edges as WorkflowEdge[]);
      scheduleSave(snapshot.nodes as WorkflowNode[], snapshot.edges as WorkflowEdge[]);
      forceBump();
    });
  }, [history, nodes, edges, setNodes, setEdges, scheduleSave]);

  const redo = useCallback(() => {
    history.redo({ nodes, edges }, (snapshot) => {
      setNodes(snapshot.nodes as WorkflowNode[]);
      setEdges(snapshot.edges as WorkflowEdge[]);
      scheduleSave(snapshot.nodes as WorkflowNode[], snapshot.edges as WorkflowEdge[]);
      forceBump();
    });
  }, [history, nodes, edges, setNodes, setEdges, scheduleSave]);

  // --- Actions ---
  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      // Cycle detection
      const wouldCycle = (source: string, target: string): boolean => {
        const adj = new Map<string, string[]>();
        for (const e of edges) {
          if (!adj.has(e.source)) adj.set(e.source, []);
          adj.get(e.source)!.push(e.target);
        }
        if (!adj.has(source)) adj.set(source, []);
        adj.get(source)!.push(target);
        const visited = new Set<string>();
        const queue = [target];
        while (queue.length > 0) {
          const n = queue.shift()!;
          if (n === source) return true;
          if (visited.has(n)) continue;
          visited.add(n);
          for (const next of adj.get(n) ?? []) queue.push(next);
        }
        return false;
      };

      if (wouldCycle(connection.source, connection.target)) return;

      const nextEdges = addEdge(connection, edges) as WorkflowEdge[];
      commit(nodes, nextEdges);
    },
    [nodes, edges, commit],
  );

  const workflowBackend = workflow.model_config?.backend ?? "";
  const workflowModel = workflow.model_config?.model ?? "";

  const addNode = useCallback(
    (type: NodeType, position: { x: number; y: number }) => {
      const def = NODE_REGISTRY.find((d) => d.type === type);
      if (!def) return;

      // agent_step inherits the workflow's default backend/model so users
      // don't have to set it every time. They can still override per-node.
      const data: NodeData =
        type === "agent_step" && workflowBackend && workflowModel
          ? {
              ...(def.defaultData as object),
              model_config: { backend: workflowBackend, model: workflowModel },
            } as NodeData
          : ({ ...def.defaultData } as NodeData);

      const newNode: WorkflowNode = {
        id: `${type}_${Date.now()}`,
        type,
        position,
        data,
        selected: true,
      };
      // Deselect all existing nodes, select only the new one
      const deselected = nodes.map((n) => (n.selected ? { ...n, selected: false } : n));
      commit([...deselected, newNode], edges);
    },
    [nodes, edges, commit, workflowBackend, workflowModel],
  );

  const deleteSelected = useCallback(() => {
    const selectedNodeIds = new Set(nodes.filter((n) => n.selected).map((n) => n.id));
    const selectedEdgeIds = new Set(edges.filter((e) => e.selected).map((e) => e.id));
    if (selectedNodeIds.size === 0 && selectedEdgeIds.size === 0) return;

    const nextNodes = nodes.filter((n) => !n.selected);
    const nextEdges = edges.filter(
      (e) =>
        !selectedEdgeIds.has(e.id) &&
        !selectedNodeIds.has(e.source) &&
        !selectedNodeIds.has(e.target),
    );
    commit(nextNodes, nextEdges);
  }, [nodes, edges, commit]);

  // Apply an assistant-generated plan atomically: one history entry for
  // the whole batch, so a single Ctrl+Z reverts every op at once.
  const applyPlan = useCallback(
    (plan: PlanOp[]): { ok: boolean; error?: string } => {
      const err = validatePlan(plan, nodes, edges);
      if (err) return { ok: false, error: err };
      const next = applyPlanPure(plan, nodes, edges);
      commit(next.nodes, next.edges);
      return { ok: true };
    },
    [nodes, edges, commit],
  );

  // Inspector: commit on blur. Pushes to history so text edits are undo-able,
  // but only once per field focus (not per keystroke).
  const updateNodeData = useCallback(
    (nodeId: string, key: string, value: unknown) => {
      const nextNodes = nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, [key]: value } } : n,
      );
      commit(nextNodes, edges);
    },
    [nodes, edges, commit],
  );

  return (
    <WorkflowBuilderContext.Provider
      value={{
        workflowId: workflow.id,
        workflowName: workflow.name,
        isReadOnly,
        nodes,
        edges,
        onNodesChange,
        onEdgesChange,
        onNodeDragStart,
        onNodeDragStop,
        onConnect,
        addNode,
        updateNodeData,
        deleteSelected,
        applyPlan,
        workflowModelBackend: workflowBackend,
        workflowModelName: workflowModel,
        selectedNodeId,
        undo,
        redo,
        canUndo: history.canUndo(),
        canRedo: history.canRedo(),
        cancelPendingSave,
      }}
    >
      {children}
    </WorkflowBuilderContext.Provider>
  );
}
