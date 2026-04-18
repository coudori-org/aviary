"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Bot, Play, Check, X, CircleDot, Loader2, Globe, GitBranch, Layers, Filter, FileText, Send, Square, RefreshCw } from "@/components/icons";
import { ChatTranscript } from "@/features/chat/components/chat-transcript";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { useVersionSelection } from "@/features/workflows/providers/version-selection-provider";
import { useWorkflowRun, type NodeRunData } from "@/features/workflows/hooks/use-workflow-run";
import { cn } from "@/lib/utils";

const TRIGGER_TYPES = new Set(["manual_trigger", "webhook_trigger"]);

const NODE_ICONS: Record<string, React.ReactNode> = {
  manual_trigger: <Play size={13} strokeWidth={2} />,
  webhook_trigger: <Globe size={13} strokeWidth={1.75} />,
  agent_step: <Bot size={13} strokeWidth={1.75} />,
  condition: <GitBranch size={13} strokeWidth={1.75} />,
  merge: <Layers size={13} strokeWidth={1.75} />,
  payload_parser: <Filter size={13} strokeWidth={1.75} />,
  template: <FileText size={13} strokeWidth={1.75} />,
};

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  running: { icon: <Loader2 size={11} className="animate-spin" />, color: "text-info", label: "Running" },
  completed: { icon: <Check size={11} strokeWidth={3} />, color: "text-success", label: "Done" },
  failed: { icon: <X size={11} strokeWidth={3} />, color: "text-danger", label: "Failed" },
  skipped: { icon: <CircleDot size={11} />, color: "text-fg-disabled", label: "Skipped" },
};

function Collapsible({ label, children, defaultOpen = false }: { label: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-[10px] font-medium text-fg-disabled uppercase tracking-wider hover:text-fg-muted transition-colors"
      >
        <span className={cn("transition-transform", open && "rotate-90")}>▸</span>
        {label}
      </button>
      {open && <div className="mt-1">{children}</div>}
    </div>
  );
}

function DataPreview({ label, data, defaultOpen = false }: { label: string; data: unknown; defaultOpen?: boolean }) {
  if (data === null || data === undefined) return null;
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  if (!text || text === "{}") return null;

  return (
    <Collapsible label={label} defaultOpen={defaultOpen}>
      <pre className="text-[11px] text-fg-muted bg-white/[0.02] rounded-md px-2 py-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono">
        {text}
      </pre>
    </Collapsible>
  );
}

function NodeStatusStrip({
  nodeType, nodeLabel, status,
}: {
  nodeType: string; nodeLabel: string; status: NodeRunData["status"];
}) {
  const statusCfg = STATUS_CONFIG[status];
  return (
    <div className="shrink-0 flex items-center gap-2 px-3 py-2 border-b border-white/[0.06]">
      <span className="text-fg-muted">{NODE_ICONS[nodeType] ?? <CircleDot size={13} />}</span>
      <span className="text-[12px] font-medium text-fg-primary flex-1 truncate">{nodeLabel}</span>
      {statusCfg && (
        <span className={cn("flex items-center gap-1 text-[10px] font-medium", statusCfg.color)}>
          {statusCfg.icon}
          {statusCfg.label}
        </span>
      )}
    </div>
  );
}

function NodeCard({
  nodeType, nodeLabel, data,
}: {
  nodeType: string; nodeLabel: string;
  data: NodeRunData;
}) {
  const status = data.status;
  return (
    <div className={cn(
      "rounded-lg border border-white/[0.06] bg-[rgb(16_17_17)] overflow-hidden",
      status === "running" && "border-info/20",
    )}>
      <NodeStatusStrip nodeType={nodeType} nodeLabel={nodeLabel} status={status} />
      <div className="px-3 py-2 space-y-2">
        <DataPreview label="Input" data={data.input_data} />
        {(status === "completed" || status === "running") && (
          <DataPreview label="Output" data={data.output_data} defaultOpen />
        )}
        {status === "skipped" && <p className="text-[11px] text-fg-disabled">Skipped (condition branch)</p>}
        {status === "failed" && data.error && (
          <p className="text-[11px] text-danger">{data.error}</p>
        )}
      </div>
    </div>
  );
}

function RunFooter({
  run, showResume, resumeLabel,
}: {
  run: ReturnType<typeof useWorkflowRun>;
  showResume: boolean;
  resumeLabel: string;
}) {
  const rs = run.runStatus;
  if (rs !== "completed" && rs !== "failed" && rs !== "cancelled") return null;
  const terminal = rs === "completed" ? "success" : "danger";
  const label = rs === "completed"
    ? (showResume ? "Completed — new nodes pending" : "Completed")
    : rs === "failed" ? "Failed" : "Cancelled";
  return (
    <div className="shrink-0 border-t border-white/[0.06] flex flex-col items-center gap-1.5 px-3 py-2">
      <p className={cn("text-[11px]", terminal === "success" ? "text-success" : "text-danger")}>{label}</p>
      {showResume && (
        <button
          type="button"
          onClick={run.resume}
          className="flex items-center gap-1.5 rounded-md border border-info/30 bg-info/10 px-2.5 py-1 text-[11px] font-medium text-info hover:bg-info/20 transition-colors"
          title="Start a new run that carries forward completed outputs"
        >
          <RefreshCw size={11} strokeWidth={2} />
          {resumeLabel}
        </button>
      )}
    </div>
  );
}

function TriggerInputBar({
  run, isWebhook, runType,
}: {
  run: ReturnType<typeof useWorkflowRun>;
  isWebhook: boolean;
  runType: "draft" | "deployed";
}) {
  const [inputValue, setInputValue] = useState("");

  const handleSubmit = useCallback(() => {
    const text = inputValue.trim();
    if (!text || run.isRunning) return;
    const triggerData = isWebhook
      ? (() => { try { return JSON.parse(text); } catch { return { raw: text }; } })()
      : { text };
    run.trigger(triggerData, runType);
    setInputValue("");
  }, [inputValue, run, isWebhook, runType]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="shrink-0 border-t border-white/[0.06] px-3 py-2">
      <div className="flex items-end gap-2">
        <textarea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={run.isRunning}
          placeholder={isWebhook ? '{"key": "value"}' : "Type a message to start the workflow…"}
          rows={1}
          className={cn(
            "flex-1 resize-none rounded-md bg-canvas px-3 py-2 text-[13px] text-fg-primary",
            "border border-white/[0.08] placeholder:text-fg-disabled",
            "focus:outline-none focus:border-info focus:ring-1 focus:ring-info/30",
            "disabled:opacity-40",
          )}
        />
        {run.isRunning ? (
          <button
            type="button"
            onClick={run.cancel}
            className="shrink-0 flex items-center justify-center h-9 w-9 rounded-md bg-danger/10 text-danger hover:bg-danger/20 transition-colors"
            title="Cancel run"
          >
            <Square size={14} strokeWidth={2.5} />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!inputValue.trim()}
            className="shrink-0 flex items-center justify-center h-9 w-9 rounded-md bg-brand/10 text-brand hover:bg-brand/20 transition-colors disabled:opacity-30"
            title="Start run"
          >
            <Send size={14} strokeWidth={2} />
          </button>
        )}
      </div>
    </div>
  );
}

function RunningStatusBar({ run }: { run: ReturnType<typeof useWorkflowRun> }) {
  if (!run.isRunning) return null;
  return (
    <div className="shrink-0 flex items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2 bg-info/[0.04]">
      <span className="flex items-center gap-2 text-[11px] text-info">
        <Loader2 size={12} className="animate-spin" />
        Workflow running…
      </span>
      <button
        type="button"
        onClick={run.cancel}
        className="flex items-center gap-1 rounded-md bg-danger/10 px-2 py-1 text-[11px] font-medium text-danger hover:bg-danger/20 transition-colors"
      >
        <Square size={10} strokeWidth={2.5} />
        Cancel
      </button>
    </div>
  );
}

interface TestPanelProps {
  run: ReturnType<typeof useWorkflowRun>;
}

export function TestPanel({ run }: TestPanelProps) {
  const { nodes: graphNodes, selectedNodeId } = useWorkflowBuilder();
  const { isDraft, isLatestVersionSelected } = useVersionSelection();
  // Trigger is gated to draft or latest-deployed: past versions would
  // silently run the LATEST on the backend (misleading), so the user
  // must roll back via Edit first.
  const canTrigger = isDraft || isLatestVersionSelected;
  const runType: "draft" | "deployed" = isDraft ? "draft" : "deployed";

  const triggerNode = graphNodes.find((n) => TRIGGER_TYPES.has(n.type ?? ""));
  const selectedNode = selectedNodeId ? graphNodes.find((n) => n.id === selectedNodeId) : null;
  const focusNode = selectedNode ?? triggerNode ?? null;
  const isTriggerFocus = !!focusNode && TRIGGER_TYPES.has(focusNode.type ?? "");

  const focusLabel = focusNode
    ? ((focusNode.data as Record<string, unknown>)?.label as string) ?? focusNode.id
    : "";
  const focusType = focusNode?.type ?? "unknown";
  const focusData: NodeRunData | null = focusNode
    ? (run.nodeData[focusNode.id]
        ?? (focusNode.id in run.nodeStatuses ? { status: run.nodeStatuses[focusNode.id] } : null))
    : null;

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [focusData?.status, focusData?.output_data]);

  if (!focusNode) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-[12px] text-fg-disabled">
        Add a trigger node to test this workflow.
      </div>
    );
  }

  // Resume is offered whenever the current graph still has unfinished
  // nodes — after a fail/cancel, or when the user added new nodes after
  // a successful run.
  const hasUnfinishedLiveNodes = graphNodes.some(
    (n) => (run.nodeData[n.id]?.status ?? run.nodeStatuses[n.id]) !== "completed",
  );
  const showResume = run.canResume && hasUnfinishedLiveNodes;
  const resumeLabel =
    run.runStatus === "failed"
      ? "Resume from failed step"
      : run.runStatus === "cancelled"
        ? "Resume from cancelled step"
        : "Continue with new nodes";

  const isAgentStepFocus = focusType === "agent_step" && !!focusData?.session_id;

  return (
    <div className="flex h-full flex-col">
      {!isTriggerFocus && <RunningStatusBar run={run} />}

      {isAgentStepFocus ? (
        // `live` gates the WS connection to running steps only — a
        // terminal-state transcript doesn't need (or want) a live socket.
        <>
          <NodeStatusStrip nodeType={focusType} nodeLabel={focusLabel} status={focusData!.status} />
          <div className="flex-1 min-h-0">
            <ChatTranscript
              sessionId={focusData!.session_id!}
              live={focusData!.status === "running"}
            />
          </div>
        </>
      ) : (
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
          {focusData ? (
            <NodeCard
              nodeType={focusType}
              nodeLabel={focusLabel}
              data={focusData}
            />
          ) : (
            <p className="text-center text-[12px] text-fg-disabled py-8">
              {isTriggerFocus
                ? "Send an input to start testing."
                : run.runStatus === "idle"
                  ? "No run yet. Select the trigger node to start one."
                  : "This node hasn't executed yet."}
            </p>
          )}
        </div>
      )}

      <RunFooter run={run} showResume={showResume} resumeLabel={resumeLabel} />

      {isTriggerFocus && (
        canTrigger ? (
          <TriggerInputBar
            run={run}
            isWebhook={focusType === "webhook_trigger"}
            runType={runType}
          />
        ) : (
          <div className="shrink-0 border-t border-white/[0.06] px-3 py-3 type-caption text-fg-muted text-center">
            Viewing a past version — click Edit in the toolbar to roll back
            before running.
          </div>
        )
      )}
    </div>
  );
}
