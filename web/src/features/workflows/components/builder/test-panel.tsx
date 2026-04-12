"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Bot, Play, Check, X, CircleDot, Loader2, Globe, GitBranch, Layers, Filter, FileText, Send, Square } from "@/components/icons";
import { TextBlockView } from "@/features/chat/components/blocks/text-block";
import { ThinkingChip } from "@/features/chat/components/blocks/thinking-chip";
import { ToolCallCard } from "@/features/chat/components/blocks/tool-call-card";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { useWorkflowRun, type NodeLogEntry, type NodeRunStatus, type NodeRunData } from "@/features/workflows/hooks/use-workflow-run";
import { cn } from "@/lib/utils";
import type { StreamBlock, ToolCallBlock } from "@/types";

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

function Collapsible({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
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

function DataPreview({ label, data }: { label: string; data: unknown }) {
  if (data === null || data === undefined) return null;
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  if (!text || text === "{}") return null;

  return (
    <Collapsible label={label}>
      <pre className="text-[11px] text-fg-muted bg-white/[0.02] rounded-md px-2 py-1.5 overflow-x-auto whitespace-pre-wrap break-words font-mono">
        {text}
      </pre>
    </Collapsible>
  );
}

function NodeCard({
  nodeId, nodeType, nodeLabel, data, logs, isLast,
}: {
  nodeId: string; nodeType: string; nodeLabel: string;
  data: NodeRunData; logs: NodeLogEntry[]; isLast: boolean;
}) {
  const status = data.status;
  const statusCfg = STATUS_CONFIG[status];
  const isAgentStep = nodeType === "agent_step";

  // Build streaming blocks from agent step logs
  const blocks: StreamBlock[] = [];
  if (isAgentStep) {
    let thinkingContent = "";
    let textContent = "";
    for (const log of logs) {
      if (log.log_type === "thinking") {
        thinkingContent += log.content ?? "";
      } else if (log.log_type === "chunk") {
        if (thinkingContent) {
          blocks.push({ type: "thinking", id: `t-${blocks.length}`, content: thinkingContent });
          thinkingContent = "";
        }
        textContent += log.content ?? "";
      } else if (log.log_type === "tool_use") {
        if (thinkingContent) { blocks.push({ type: "thinking", id: `t-${blocks.length}`, content: thinkingContent }); thinkingContent = ""; }
        if (textContent) { blocks.push({ type: "text", id: `x-${blocks.length}`, content: textContent }); textContent = ""; }
        blocks.push({ type: "tool_call", id: `tc-${blocks.length}`, name: log.name ?? "unknown", input: (log.input ?? {}) as Record<string, unknown>, status: "running" } as ToolCallBlock);
      } else if (log.log_type === "tool_result") {
        const lastTool = [...blocks].reverse().find((b) => b.type === "tool_call") as ToolCallBlock | undefined;
        if (lastTool) { lastTool.status = "complete"; lastTool.result = log.content; }
      }
    }
    if (thinkingContent) blocks.push({ type: "thinking", id: `t-${blocks.length}`, content: thinkingContent });
    if (textContent) blocks.push({ type: "text", id: `x-${blocks.length}`, content: textContent });
  }

  return (
    <div className={cn(
      "rounded-lg border border-white/[0.06] bg-[rgb(16_17_17)] overflow-hidden",
      isLast && status === "running" && "border-info/20",
    )}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-white/[0.02]">
        <span className="text-fg-muted">{NODE_ICONS[nodeType] ?? <CircleDot size={13} />}</span>
        <span className="text-[12px] font-medium text-fg-primary flex-1 truncate">{nodeLabel}</span>
        {statusCfg && (
          <span className={cn("flex items-center gap-1 text-[10px] font-medium", statusCfg.color)}>
            {statusCfg.icon}
            {statusCfg.label}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="px-3 py-2 space-y-2">
        {/* Input ports */}
        <DataPreview label="Input" data={data.input_data} />

        {/* Agent Step streaming content */}
        {isAgentStep && blocks.length > 0 && (
          <Collapsible label="Agent Response">
            <div className="space-y-2">
              {blocks.map((block) => {
                if (block.type === "thinking") return <ThinkingChip key={block.id} content={block.content} isActive={status === "running"} />;
                if (block.type === "text") return <TextBlockView key={block.id} content={block.content} />;
                if (block.type === "tool_call") return <ToolCallCard key={block.id} block={block as ToolCallBlock} />;
                return null;
              })}
            </div>
          </Collapsible>
        )}

        {isAgentStep && blocks.length === 0 && status === "running" && (
          <p className="text-[11px] text-fg-disabled animate-pulse">Processing…</p>
        )}

        {/* Output ports */}
        {status === "completed" && <DataPreview label="Output" data={data.output_data} />}

        {status === "skipped" && <p className="text-[11px] text-fg-disabled">Skipped (condition branch)</p>}

        {status === "failed" && data.error && (
          <p className="text-[11px] text-danger">{data.error}</p>
        )}
      </div>
    </div>
  );
}

// --- Test Panel ---
interface TestPanelProps {
  run: ReturnType<typeof useWorkflowRun>;
}

export function TestPanel({ run }: TestPanelProps) {
  const { nodes: graphNodes } = useWorkflowBuilder();
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [inputValue, setInputValue] = useState("");

  const triggerNode = graphNodes.find((n) => n.type === "manual_trigger" || n.type === "webhook_trigger");
  const isWebhook = triggerNode?.type === "webhook_trigger";

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [run.nodeStatuses, run.logs]);

  const handleSubmit = useCallback(() => {
    const text = inputValue.trim();
    if (!text || run.isRunning) return;
    const triggerData = isWebhook
      ? (() => { try { return JSON.parse(text); } catch { return { raw: text }; } })()
      : { text };
    run.trigger(triggerData);
    setInputValue("");
  }, [inputValue, run, isWebhook]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Build node cards in execution order
  const executionOrder = Object.keys(run.nodeStatuses);
  const cards = executionOrder.map((nodeId) => {
    const graphNode = graphNodes.find((n) => n.id === nodeId);
    return {
      nodeId,
      nodeType: graphNode?.type ?? "unknown",
      label: (graphNode?.data as Record<string, unknown>)?.label as string ?? nodeId,
      data: run.nodeData[nodeId] ?? { status: run.nodeStatuses[nodeId] },
      logs: run.logs.filter((l) => l.node_id === nodeId),
    };
  });

  return (
    <div className="flex h-full flex-col">
      {/* Card list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {run.runStatus === "idle" && (
          <p className="text-center text-[12px] text-fg-disabled py-8">
            {isWebhook ? "Enter a JSON payload to test" : "Send a message to test"}
          </p>
        )}

        {cards.map((c, i) => (
          <NodeCard
            key={c.nodeId}
            nodeId={c.nodeId}
            nodeType={c.nodeType}
            nodeLabel={c.label}
            data={c.data}
            logs={c.logs}
            isLast={i === cards.length - 1}
          />
        ))}

        {run.runStatus === "completed" && (
          <p className="text-center text-[11px] text-success py-1">Completed</p>
        )}
        {run.runStatus === "failed" && (
          <p className="text-center text-[11px] text-danger py-1">Failed</p>
        )}
      </div>

      {/* Simple input */}
      <div className="border-t border-white/[0.06] px-3 py-2">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={run.isRunning}
            placeholder={isWebhook ? '{"key": "value"}' : "Type a message…"}
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
            >
              <Square size={14} strokeWidth={2.5} />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!inputValue.trim()}
              className="shrink-0 flex items-center justify-center h-9 w-9 rounded-md bg-brand/10 text-brand hover:bg-brand/20 transition-colors disabled:opacity-30"
            >
              <Send size={14} strokeWidth={2} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
