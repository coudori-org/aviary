"use client";

import { useCallback, useRef, useEffect, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  type DefaultEdgeOptions,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "./builder.css";

import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { useWorkflowRun } from "@/features/workflows/hooks/use-workflow-run";
import { RunStatusProvider, useAllNodeRunStatuses } from "@/features/workflows/providers/run-status-provider";
import { NodePalette } from "./node-palette";
import { InspectorPanel } from "./inspector-panel";
import { Toolbar } from "./toolbar";
import { ConsolePanel } from "./console-panel";
import { RunDialog } from "./run-dialog";
import { ManualTriggerNode, WebhookTriggerNode } from "./nodes/trigger-node";
import { AgentStepNode } from "./nodes/agent-step-node";
import { ConditionNode, MergeNode } from "./nodes/control-nodes";
import { PayloadParserNode, TemplateNode } from "./nodes/transform-nodes";
import type { NodeType } from "@/features/workflows/lib/types";

const defaultEdgeOptions: DefaultEdgeOptions = {
  animated: true,
};

const nodeTypes = {
  manual_trigger: ManualTriggerNode,
  webhook_trigger: WebhookTriggerNode,
  agent_step: AgentStepNode,
  condition: ConditionNode,
  merge: MergeNode,
  payload_parser: PayloadParserNode,
  template: TemplateNode,
};

function Canvas() {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onNodeDragStart,
    onNodeDragStop,
    onConnect,
    addNode,
    undo,
    redo,
    deleteSelected,
  } = useWorkflowBuilder();

  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();
  const nodeRunStatuses = useAllNodeRunStatuses();

  const miniMapNodeColor = useCallback(
    (node: { id: string }) => {
      const status = nodeRunStatuses[node.id];
      switch (status) {
        case "running": return "rgba(85,179,255,0.5)";
        case "completed": return "rgba(95,201,146,0.5)";
        case "failed": return "rgba(255,99,99,0.5)";
        case "skipped": return "rgba(255,255,255,0.05)";
        default: return "rgba(255,255,255,0.08)";
      }
    },
    [nodeRunStatuses],
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (key === "z" && (e.ctrlKey || e.metaKey) && e.shiftKey) {
        e.preventDefault();
        redo();
      } else if (key === "y" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        redo();
      } else if (key === "z" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        undo();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        const target = e.target as HTMLElement;
        if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
        deleteSelected();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo, deleteSelected]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData("application/workflow-node-type") as NodeType;
      if (!type || !reactFlowWrapper.current) return;

      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      addNode(type, position);
    },
    [addNode, screenToFlowPosition],
  );

  return (
    <div ref={reactFlowWrapper} className="flex-1">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStart={onNodeDragStart}
        onNodeDragStop={onNodeDragStop}
        onDragOver={onDragOver}
        onDrop={onDrop}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        fitView
        deleteKeyCode={null}
        edgesFocusable
        edgesReconnectable
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} color="rgba(255,255,255,0.025)" />
        <Controls />
        <MiniMap
          nodeColor={miniMapNodeColor}
          maskColor="rgba(0,0,0,0.7)"
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}

export function WorkflowBuilder() {
  const { workflowId, addNode } = useWorkflowBuilder();
  const run = useWorkflowRun(workflowId);
  const [runDialogOpen, setRunDialogOpen] = useState(false);

  const handlePaletteAdd = useCallback(
    (type: NodeType) => {
      addNode(type, { x: 300, y: 200 + Math.random() * 100 });
    },
    [addNode],
  );

  const handleRunRequest = useCallback(() => {
    setRunDialogOpen(true);
  }, []);

  const handleRunConfirm = useCallback(
    (triggerData: Record<string, unknown>) => {
      run.trigger(triggerData);
    },
    [run],
  );

  return (
    <RunStatusProvider nodeStatuses={run.nodeStatuses}>
      <div className="flex h-full flex-col">
        <Toolbar runStatus={run.runStatus} onRun={handleRunRequest} onCancel={run.cancel} />
        <div className="flex flex-1 overflow-hidden">
          <NodePalette onAddNode={handlePaletteAdd} />
          <div className="flex flex-1 flex-col overflow-hidden">
            <ReactFlowProvider>
              <div className="flex flex-1 overflow-hidden">
                <Canvas />
                <InspectorPanel />
              </div>
            </ReactFlowProvider>
            <ConsolePanel logs={run.logs} runStatus={run.runStatus} error={run.error} />
          </div>
        </div>
      </div>
      <RunDialog open={runDialogOpen} onClose={() => setRunDialogOpen(false)} onRun={handleRunConfirm} />
    </RunStatusProvider>
  );
}
