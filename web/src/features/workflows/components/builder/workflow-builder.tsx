"use client";

import { useCallback, useRef, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
import { useTheme } from "@/features/theme/theme-provider";
import {
  useVersionSelection,
  DRAFT_SELECTION,
} from "@/features/workflows/providers/version-selection-provider";
import { useWorkflowRun } from "@/features/workflows/hooks/use-workflow-run";
import { RunStatusProvider, useAllNodeRunStatuses } from "@/features/workflows/providers/run-status-provider";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { routes } from "@/lib/constants/routes";
import { SettingsPanel } from "./settings-panel";
import { NodePalette } from "./node-palette";
import { InspectorPanel } from "./inspector-panel";
import { TestPanel } from "./test-panel";
import { RunHistoryPanel } from "./run-history-panel";
import { Toolbar } from "./toolbar";
import { AssistantPanel } from "./assistant-panel";
import { ManualTriggerNode, WebhookTriggerNode } from "./nodes/trigger-node";
import { AgentStepNode } from "./nodes/agent-step-node";
import { ConditionNode, MergeNode } from "./nodes/control-nodes";
import { PayloadParserNode, TemplateNode } from "./nodes/transform-nodes";
import type { NodeType } from "@/features/workflows/lib/types";
import { cn } from "@/lib/utils";

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

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 py-1.5 text-[11px] font-medium transition-colors",
        active ? "text-fg-primary border-b-2 border-accent" : "text-fg-muted hover:text-fg-secondary",
      )}
    >
      {children}
    </button>
  );
}

function Canvas({ readOnly }: { readOnly: boolean }) {
  const {
    nodes, edges, onNodesChange, onEdgesChange,
    onNodeDragStart, onNodeDragStop, onConnect,
    addNode, undo, redo, deleteSelected,
  } = useWorkflowBuilder();

  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();
  const nodeRunStatuses = useAllNodeRunStatuses();
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const miniMapNodeColor = useCallback(
    (node: { id: string }) => {
      const status = nodeRunStatuses[node.id];
      switch (status) {
        case "running": return "rgba(91,141,239,0.65)";
        case "completed": return "rgba(74,222,128,0.6)";
        case "failed": return "rgba(240,122,122,0.6)";
        case "skipped":
          return isDark ? "rgba(255,255,255,0.05)" : "rgba(20,22,28,0.06)";
        default:
          return isDark ? "rgba(255,255,255,0.10)" : "rgba(20,22,28,0.18)";
      }
    },
    [nodeRunStatuses, isDark],
  );

  const maskColor = isDark ? "rgba(0,0,0,0.7)" : "rgba(60,55,45,0.18)";
  const backgroundColor = isDark ? "rgba(255,255,255,0.16)" : "rgba(20,22,28,0.20)";

  useEffect(() => {
    if (readOnly) return;
    const handler = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (key === "z" && (e.ctrlKey || e.metaKey) && e.shiftKey) { e.preventDefault(); redo(); }
      else if (key === "y" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); redo(); }
      else if (key === "z" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); undo(); }
      else if (e.key === "Delete" || e.key === "Backspace") {
        const t = e.target as HTMLElement;
        if (t.tagName === "INPUT" || t.tagName === "TEXTAREA") return;
        deleteSelected();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo, deleteSelected, readOnly]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    if (readOnly) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, [readOnly]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      if (readOnly) return;
      e.preventDefault();
      const type = e.dataTransfer.getData("application/workflow-node-type") as NodeType;
      if (!type || !reactFlowWrapper.current) return;
      addNode(type, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
    },
    [addNode, screenToFlowPosition, readOnly],
  );

  return (
    <div ref={reactFlowWrapper} className="flex-1">
      <ReactFlow
        nodes={nodes} edges={edges}
        // Keep change handlers wired in read-only too: ReactFlow routes
        // selection + measurement through onNodesChange, so dropping it
        // breaks node click-selection, minimap, and fitView. Edit
        // restriction happens via the `nodesDraggable / nodesConnectable
        // / edgesReconnectable` flags below instead.
        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStart={onNodeDragStart} onNodeDragStop={onNodeDragStop}
        onDragOver={onDragOver} onDrop={onDrop}
        nodeTypes={nodeTypes} defaultEdgeOptions={defaultEdgeOptions}
        fitView deleteKeyCode={null}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        edgesFocusable={!readOnly}
        edgesReconnectable={!readOnly}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1.4} color={backgroundColor} />
        <Controls />
        <MiniMap nodeColor={miniMapNodeColor} maskColor={maskColor} pannable zoomable />
      </ReactFlow>
    </div>
  );
}

type LeftTab = "nodes" | "runs" | "settings";

function LeftPanel({
  readOnly, onAddNode, run, onOpenRun,
}: {
  readOnly: boolean;
  onAddNode: (type: NodeType) => void;
  run: ReturnType<typeof useWorkflowRun>;
  onOpenRun: () => void;
}) {
  const [tab, setTab] = useState<LeftTab>(readOnly ? "runs" : "nodes");

  return (
    <div className="w-[240px] shrink-0 flex flex-col border-r border-border-subtle bg-surface">
      <div className="flex border-b border-border-subtle">
        {!readOnly && (
          <TabButton active={tab === "nodes"} onClick={() => setTab("nodes")}>Nodes</TabButton>
        )}
        <TabButton active={tab === "runs"} onClick={() => setTab("runs")}>Runs</TabButton>
        <TabButton active={tab === "settings"} onClick={() => setTab("settings")}>Settings</TabButton>
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === "nodes" && !readOnly && <NodePalette onAddNode={onAddNode} />}
        {tab === "runs" && <RunHistoryPanel run={run} onOpenRun={onOpenRun} />}
        {tab === "settings" && <SettingsPanel />}
      </div>
    </div>
  );
}

function PanelResizeHandle({ onResize }: { onResize: (delta: number) => void }) {
  const dragging = useRef(false);
  const lastX = useRef(0);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    lastX.current = e.clientX;
    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      onResize(lastX.current - ev.clientX);
      lastX.current = ev.clientX;
    };
    const onMouseUp = () => {
      dragging.current = false;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }, [onResize]);

  return (
    <div
      onMouseDown={onMouseDown}
      className="absolute left-0 top-0 h-full w-1 cursor-col-resize z-10 hover:bg-accent-soft active:bg-accent-border transition-colors"
    />
  );
}

const RIGHT_MIN = 300;
const RIGHT_MAX = 960;
const RIGHT_DEFAULT = 340;

type RightTab = "inspector" | "test";

function RightPanel({
  run, tab, onTabChange,
}: {
  run: ReturnType<typeof useWorkflowRun>;
  tab: RightTab;
  onTabChange: (tab: RightTab) => void;
}) {
  const [width, setWidth] = useState(RIGHT_DEFAULT);
  const handleResize = useCallback((delta: number) => {
    setWidth((w) => Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, w + delta)));
  }, []);

  return (
    <div
      className="relative flex flex-col border-l border-border-subtle bg-surface"
      style={{ width, minWidth: RIGHT_MIN, flexShrink: 0 }}
    >
      <PanelResizeHandle onResize={handleResize} />
      <div className="flex shrink-0 border-b border-border-subtle">
        <TabButton active={tab === "inspector"} onClick={() => onTabChange("inspector")}>Inspector</TabButton>
        <TabButton active={tab === "test"} onClick={() => onTabChange("test")}>Test</TabButton>
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === "inspector" && <InspectorPanel />}
        {tab === "test" && <TestPanel run={run} />}
      </div>
    </div>
  );
}

export function WorkflowBuilder() {
  const router = useRouter();
  const { workflowId, addNode, cancelPendingSave } = useWorkflowBuilder();
  const {
    isDraft,
    isLatestVersionSelected,
    selectedVersionDefinition,
    deepLinkRunId,
    mutateAndNavigate,
  } = useVersionSelection();
  const run = useWorkflowRun(workflowId);
  const [deploying, setDeploying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const readOnly = !isDraft;

  const [rightTab, setRightTab] = useState<RightTab>(
    deepLinkRunId ? "test" : "inspector",
  );
  // Fire viewRun only on runId transitions so user-initiated tab
  // switches don't clobber. Boolean guard would only work once; ref
  // tracks the last handled value.
  const lastHandledRunIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!deepLinkRunId) return;
    if (lastHandledRunIdRef.current === deepLinkRunId) return;
    lastHandledRunIdRef.current = deepLinkRunId;
    void run.viewRun(deepLinkRunId);
    setRightTab("test");
  }, [deepLinkRunId, run]);

  const handlePaletteAdd = useCallback(
    (type: NodeType) => {
      addNode(type, { x: 300, y: 200 + Math.random() * 100 });
    },
    [addNode],
  );

  const handleDeploy = useCallback(async () => {
    setDeploying(true);
    try {
      await workflowsApi.deploy(workflowId);
      await mutateAndNavigate((latestId) => latestId ?? DRAFT_SELECTION);
    } finally {
      setDeploying(false);
    }
  }, [workflowId, mutateAndNavigate]);

  const handleEdit = useCallback(async () => {
    // Rollback: when editing a past version, push that snapshot into
    // the draft slot first so the editable view reflects v1 content.
    if (!isLatestVersionSelected && selectedVersionDefinition) {
      await workflowsApi.update(workflowId, {
        definition: selectedVersionDefinition as unknown as Record<string, unknown>,
      });
    }
    await workflowsApi.edit(workflowId);
    await mutateAndNavigate(DRAFT_SELECTION);
  }, [workflowId, isLatestVersionSelected, selectedVersionDefinition, mutateAndNavigate]);

  const handleCancelEdit = useCallback(async () => {
    if (!window.confirm("Discard draft changes and restore the latest deployed version?")) return;
    // Kill the debounced auto-save queued for the stale draft — otherwise
    // it can land after cancel-edit and overwrite the restored definition.
    cancelPendingSave();
    await workflowsApi.cancelEdit(workflowId);
    await mutateAndNavigate((latestId) => latestId ?? DRAFT_SELECTION);
  }, [workflowId, cancelPendingSave, mutateAndNavigate]);

  const handleDeleteWorkflow = useCallback(async () => {
    if (deleting) return;
    if (!window.confirm(
      "Delete this workflow? Every run, its history, and the artifact tree will be permanently removed.",
    )) return;
    setDeleting(true);
    // Stop any queued autosave from racing the delete — it would recreate
    // a draft definition after the row is already gone.
    cancelPendingSave();
    try {
      await workflowsApi.remove(workflowId);
      router.push(routes.workflows);
    } catch (err) {
      setDeleting(false);
      window.alert(err instanceof Error ? err.message : "Failed to delete workflow");
    }
  }, [deleting, cancelPendingSave, workflowId, router]);

  return (
    <RunStatusProvider nodeStatuses={run.nodeStatuses}>
      <div className="flex h-full flex-col">
        <Toolbar
          deploying={deploying}
          deletingWorkflow={deleting}
          onDeploy={handleDeploy}
          onEdit={handleEdit}
          onCancelEdit={handleCancelEdit}
          onDeleteWorkflow={handleDeleteWorkflow}
        />
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex flex-1 overflow-hidden">
            <LeftPanel
              readOnly={readOnly}
              onAddNode={handlePaletteAdd}
              run={run}
              onOpenRun={() => setRightTab("test")}
            />
            <ReactFlowProvider>
              <div className="flex flex-1 overflow-hidden">
                <Canvas readOnly={readOnly} />
                <RightPanel run={run} tab={rightTab} onTabChange={setRightTab} />
              </div>
            </ReactFlowProvider>
          </div>
          {!readOnly && <AssistantPanel />}
        </div>
      </div>
    </RunStatusProvider>
  );
}
