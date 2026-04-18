"use client";

import { createContext, useContext, useCallback, useRef } from "react";
import {
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type OnNodesChange,
  type OnEdgesChange,
} from "@xyflow/react";
import { useWorkflowHistory } from "../hooks/use-workflow-history";
import { useAutoSave } from "../hooks/use-auto-save";
import type { Workflow } from "@/types";
import type { WorkflowNode, WorkflowEdge, NodeType, NodeData } from "../lib/types";
import { NODE_REGISTRY } from "../lib/node-registry";
import { applyPlan as applyPlanPure, validatePlan, type PlanOp } from "../lib/assistant-plan";

interface WorkflowBuilderContextValue {
  workflowId: string;
  workflowName: string;
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
  isReadOnly?: boolean;
  children: React.ReactNode;
}

export function WorkflowBuilderProvider({ workflow, isReadOnly = false, children }: Props) {
  const initialNodes = (workflow.definition?.nodes ?? []) as WorkflowNode[];
  const initialEdges = (workflow.definition?.edges ?? []) as WorkflowEdge[];

  const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowNode>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<WorkflowEdge>(initialEdges);
  const history = useWorkflowHistory();
  const { scheduleSave, cancelPendingSave } = useAutoSave(workflow.id);

  const selectedNodeId = nodes.find((n) => n.selected)?.id ?? null;

  const commit = useCallback(
    (nextNodes: WorkflowNode[], nextEdges: WorkflowEdge[]) => {
      history.push({ nodes, edges });
      setNodes(nextNodes);
      setEdges(nextEdges);
      scheduleSave(nextNodes, nextEdges);
    },
    [history, nodes, edges, setNodes, setEdges, scheduleSave],
  );

  const preDragRef = useRef<{ nodes: WorkflowNode[]; edges: WorkflowEdge[] } | null>(null);

  const onNodeDragStart = useCallback(() => {
    preDragRef.current = { nodes, edges };
  }, [nodes, edges]);

  const onNodeDragStop = useCallback(() => {
    if (!preDragRef.current) return;
    const pre = preDragRef.current.nodes;
    const moved = nodes.some((n) => {
      const old = pre.find((p) => p.id === n.id);
      return old && (old.position.x !== n.position.x || old.position.y !== n.position.y);
    });
    if (moved) {
      history.push(preDragRef.current);
      scheduleSave(nodes, edges);
    }
    preDragRef.current = null;
  }, [history, nodes, edges, scheduleSave]);

  const undo = useCallback(() => {
    history.undo({ nodes, edges }, (snapshot) => {
      setNodes(snapshot.nodes as WorkflowNode[]);
      setEdges(snapshot.edges as WorkflowEdge[]);
      scheduleSave(snapshot.nodes as WorkflowNode[], snapshot.edges as WorkflowEdge[]);
    });
  }, [history, nodes, edges, setNodes, setEdges, scheduleSave]);

  const redo = useCallback(() => {
    history.redo({ nodes, edges }, (snapshot) => {
      setNodes(snapshot.nodes as WorkflowNode[]);
      setEdges(snapshot.edges as WorkflowEdge[]);
      scheduleSave(snapshot.nodes as WorkflowNode[], snapshot.edges as WorkflowEdge[]);
    });
  }, [history, nodes, edges, setNodes, setEdges, scheduleSave]);

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

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
        canUndo: history.canUndo,
        canRedo: history.canRedo,
        cancelPendingSave,
      }}
    >
      {children}
    </WorkflowBuilderContext.Provider>
  );
}
