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
import { workflowsApi, type WorkflowVersionData } from "@/features/workflows/api/workflows-api";
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
import type { Workflow } from "@/types";
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

// --- Tab Button ---
function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 py-1.5 text-[11px] font-medium transition-colors",
        active ? "text-fg-primary border-b-2 border-info" : "text-fg-disabled hover:text-fg-muted",
      )}
    >
      {children}
    </button>
  );
}

// --- Canvas ---
function Canvas({ readOnly }: { readOnly: boolean }) {
  const {
    nodes, edges, onNodesChange, onEdgesChange,
    onNodeDragStart, onNodeDragStop, onConnect,
    addNode, undo, redo, deleteSelected,
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
        // Keep change handlers wired in both modes — ReactFlow routes
        // selection state through onNodesChange too, so dropping it
        // breaks node-click selection + anything that depends on node
        // measurements (MiniMap, fitView). Edit restriction happens via
        // the nodesDraggable / nodesConnectable / edgesReconnectable
        // flags below, which stop user-initiated mutations at the
        // ReactFlow layer before any change event is dispatched.
        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStart={onNodeDragStart} onNodeDragStop={onNodeDragStop}
        onDragOver={onDragOver} onDrop={onDrop}
        nodeTypes={nodeTypes} defaultEdgeOptions={defaultEdgeOptions}
        fitView deleteKeyCode={null}
        // Deployed view is snapshot-only: selection + pan/zoom stay
        // enabled so inspector, run history, and triggers all work.
        // Only structural edits are turned off.
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        edgesFocusable={!readOnly}
        edgesReconnectable={!readOnly}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} color="rgba(255,255,255,0.025)" />
        <Controls />
        <MiniMap nodeColor={miniMapNodeColor} maskColor="rgba(0,0,0,0.7)" pannable zoomable />
      </ReactFlow>
    </div>
  );
}

// --- Left Panel (Settings + Nodes tabs) ---
function LeftPanel({
  readOnly, onAddNode,
}: {
  readOnly: boolean;
  onAddNode: (type: NodeType) => void;
}) {
  // Node palette is an editing affordance — on a deployed (snapshot)
  // view it's misleading, so collapse to Settings-only. Settings itself
  // stays read-only because it only exposes fields the builder treats
  // as safe to display regardless of status (name, description).
  const [tab, setTab] = useState<"nodes" | "settings">(readOnly ? "settings" : "nodes");

  return (
    <div className="w-56 shrink-0 flex flex-col border-r border-white/[0.06] bg-[rgb(10_11_13)]">
      <div className="flex border-b border-white/[0.06]">
        {!readOnly && (
          <TabButton active={tab === "nodes"} onClick={() => setTab("nodes")}>Nodes</TabButton>
        )}
        <TabButton active={tab === "settings"} onClick={() => setTab("settings")}>Settings</TabButton>
      </div>
      <div className="flex-1 overflow-y-auto">
        {tab === "nodes" && !readOnly ? <NodePalette onAddNode={onAddNode} /> : <SettingsPanel />}
      </div>
    </div>
  );
}

// --- Resize handle (vertical, left edge) ---
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
      className="absolute left-0 top-0 h-full w-1 cursor-col-resize z-10 hover:bg-info/30 active:bg-info/50 transition-colors"
    />
  );
}

const RIGHT_MIN = 320;
const RIGHT_MAX = 640;
const RIGHT_DEFAULT = 380;

// --- Right Panel (Inspector + Test + History tabs) ---
function RightPanel({
  workflowId, run, tab, onTabChange,
  isDraft, selectedVersionId, isLatestVersionSelected,
}: {
  workflowId: string;
  run: ReturnType<typeof useWorkflowRun>;
  tab: "inspector" | "test" | "history";
  onTabChange: (tab: "inspector" | "test" | "history") => void;
  /** True when the user is viewing the draft slot. History filters by
   *  run_type=draft; the trigger can always fire. */
  isDraft: boolean;
  /** Deployed-version mode: the history filter narrows to this
   *  WorkflowVersion.id. Null in draft mode. */
  selectedVersionId: string | null;
  /** Trigger is gated to the latest deployed version (or draft) — on a
   *  past version the backend would silently run the LATEST, which is
   *  misleading; the user rolls back via Edit first. */
  isLatestVersionSelected: boolean;
}) {
  const setTab = onTabChange;
  const [width, setWidth] = useState(RIGHT_DEFAULT);

  const handleResize = useCallback((delta: number) => {
    setWidth((w) => Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, w + delta)));
  }, []);

  return (
    <div
      className="relative flex flex-col border-l border-white/[0.06] bg-[rgb(10_11_13)]"
      style={{ width, minWidth: RIGHT_MIN, flexShrink: 0 }}
    >
      <PanelResizeHandle onResize={handleResize} />
      <div className="flex shrink-0 border-b border-white/[0.06]">
        <TabButton active={tab === "inspector"} onClick={() => setTab("inspector")}>Inspector</TabButton>
        <TabButton active={tab === "test"} onClick={() => setTab("test")}>Test</TabButton>
        <TabButton active={tab === "history"} onClick={() => setTab("history")}>History</TabButton>
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === "inspector" && <InspectorPanel />}
        {tab === "test" && (
          <TestPanel
            run={run}
            canTrigger={isDraft || isLatestVersionSelected}
            runType={isDraft ? "draft" : "deployed"}
          />
        )}
        {tab === "history" && (
          <RunHistoryPanel
            workflowId={workflowId}
            run={run}
            onOpenRun={() => setTab("test")}
            runType={isDraft ? "draft" : "deployed"}
            versionId={selectedVersionId ?? undefined}
          />
        )}
      </div>
    </div>
  );
}

// --- Main Builder ---
/** Sentinel the page uses to mean "the editable draft slot". */
const DRAFT = "draft" as const;

interface WorkflowBuilderProps {
  versions: WorkflowVersionData[];
  /** ``"draft"`` or a deployed version's id. Selection is the single
   *  source of truth for read-only, history filter, and trigger gating
   *  — there's no separate workflowStatus branching anywhere below. */
  selected: string;
  onSelect: (next: string) => void;
  isDraft: boolean;
  isLatestVersionSelected: boolean;
  /** Definition of the non-draft version currently loaded. Only set
   *  when a deployed version is selected — used to push that snapshot
   *  onto the draft slot on rollback Edit. */
  selectedVersionDefinition?: Workflow["definition"];
  /** Run to auto-load into the test panel. The page gates this to only
   *  be set when the URL's runId is consistent with ``selected`` — so
   *  a stale post-action URL can't overlay an old run's node statuses
   *  onto a fresh draft / other-version view. */
  deepLinkRunId: string | null;
  /** Refetch workflow/versions and re-point selection afterwards.
   *  Each action (Deploy / Edit / Cancel) picks where to land. */
  reloadAndSelect: (
    next: string | ((latestId: string | null) => string),
  ) => Promise<void>;
}

export function WorkflowBuilder({
  versions, selected, onSelect, isDraft, isLatestVersionSelected,
  selectedVersionDefinition, deepLinkRunId, reloadAndSelect,
}: WorkflowBuilderProps) {
  const { workflowId, addNode, cancelPendingSave } = useWorkflowBuilder();
  const run = useWorkflowRun(workflowId);
  const [deploying, setDeploying] = useState(false);
  // Cancel is only available once the workflow has been deployed at
  // least once — otherwise there's no snapshot to revert to.
  const hasPriorDeploy = versions.length > 0;
  const readOnly = !isDraft;
  // Deep-link: the page passes a runId only when the URL is coherent
  // with `selected` (so a stale post-action URL can't slip a v1 run's
  // statuses into the draft view). Fires viewRun + flips to the Test
  // tab when it flips to a new value; user-initiated tab switches
  // don't clobber because this effect only fires on runId change.
  const [rightTab, setRightTab] = useState<"inspector" | "test" | "history">(
    deepLinkRunId ? "test" : "inspector",
  );
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
      // Land on the newly-created latest version so the user sees the
      // snapshot they just published.
      await reloadAndSelect((latestId) => latestId ?? DRAFT);
    } catch {
      // TODO: show error
    } finally {
      setDeploying(false);
    }
  }, [workflowId, reloadAndSelect]);

  const handleEdit = useCallback(async () => {
    try {
      // Rollback path: the user is viewing a past version and clicks
      // Edit. Push that snapshot into the draft slot first so the draft
      // view actually holds v1's content, then flip status. When
      // editing from the latest version the slot already matches, so
      // we skip the extra PUT.
      if (!isLatestVersionSelected && selectedVersionDefinition) {
        await workflowsApi.update(workflowId, {
          definition: selectedVersionDefinition as unknown as Record<string, unknown>,
        });
      }
      await workflowsApi.edit(workflowId);
      await reloadAndSelect(DRAFT);
    } catch {
      // TODO: show error
    }
  }, [workflowId, isLatestVersionSelected, selectedVersionDefinition, reloadAndSelect]);

  const handleCancelEdit = useCallback(async () => {
    if (!window.confirm("Discard draft changes and restore the latest deployed version?")) return;
    // Kill any debounced auto-save queued for the stale draft state —
    // otherwise it can fire after cancel-edit and overwrite the
    // restored definition on the server.
    cancelPendingSave();
    try {
      await workflowsApi.cancelEdit(workflowId);
      await reloadAndSelect((latestId) => latestId ?? DRAFT);
    } catch {
      // TODO: show error
    }
  }, [workflowId, cancelPendingSave, reloadAndSelect]);

  return (
    <RunStatusProvider nodeStatuses={run.nodeStatuses}>
      <div className="flex h-full flex-col">
        <Toolbar
          deploying={deploying}
          versions={versions}
          selected={selected}
          isDraft={isDraft}
          hasPriorDeploy={hasPriorDeploy}
          onSelect={onSelect}
          onDeploy={handleDeploy}
          onEdit={handleEdit}
          onCancelEdit={handleCancelEdit}
        />
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex flex-1 overflow-hidden">
            <LeftPanel readOnly={readOnly} onAddNode={handlePaletteAdd} />
            <ReactFlowProvider>
              <div className="flex flex-1 overflow-hidden">
                <Canvas readOnly={readOnly} />
                <RightPanel
                  workflowId={workflowId}
                  run={run}
                  tab={rightTab}
                  onTabChange={setRightTab}
                  isDraft={isDraft}
                  selectedVersionId={isDraft ? null : selected}
                  isLatestVersionSelected={isLatestVersionSelected}
                />
              </div>
            </ReactFlowProvider>
          </div>
          <AssistantPanel />
        </div>
      </div>
    </RunStatusProvider>
  );
}
