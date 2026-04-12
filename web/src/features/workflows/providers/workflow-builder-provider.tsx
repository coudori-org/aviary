"use client";

import { createContext, useContext, useCallback, useRef, useState } from "react";
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

interface WorkflowBuilderContextValue {
  workflowId: string;
  workflowName: string;
  workflowStatus: string;
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
  selectedNodeId: string | null;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

const WorkflowBuilderContext = createContext<WorkflowBuilderContextValue | null>(null);

export function useWorkflowBuilder() {
  const ctx = useContext(WorkflowBuilderContext);
  if (!ctx) throw new Error("useWorkflowBuilder must be used within WorkflowBuilderProvider");
  return ctx;
}

interface Props {
  workflow: Workflow;
  children: React.ReactNode;
}

export function WorkflowBuilderProvider({ workflow, children }: Props) {
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

  const addNode = useCallback(
    (type: NodeType, position: { x: number; y: number }) => {
      const def = NODE_REGISTRY.find((d) => d.type === type);
      if (!def) return;

      const newNode: WorkflowNode = {
        id: `${type}_${Date.now()}`,
        type,
        position,
        data: { ...def.defaultData } as NodeData,
        selected: true,
      };
      // Deselect all existing nodes, select only the new one
      const deselected = nodes.map((n) => (n.selected ? { ...n, selected: false } : n));
      commit([...deselected, newNode], edges);
    },
    [nodes, edges, commit],
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
        workflowStatus: workflow.status,
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
        selectedNodeId,
        undo,
        redo,
        canUndo: history.canUndo(),
        canRedo: history.canRedo(),
      }}
    >
      {children}
    </WorkflowBuilderContext.Provider>
  );
}
