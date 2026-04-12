"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronUp, ChevronDown } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { NodeLogEntry, RunStatus } from "@/features/workflows/hooks/use-workflow-run";

interface ConsolePanelProps {
  logs: NodeLogEntry[];
  runStatus: RunStatus;
  error: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  idle: "text-fg-disabled",
  pending: "text-warning",
  running: "text-info",
  completed: "text-success",
  failed: "text-danger",
  cancelled: "text-fg-muted",
};

const DEFAULT_HEIGHT = 300;
const MIN_HEIGHT = 120;
const MAX_HEIGHT = 600;

function ResizeHandle({ onResize }: { onResize: (delta: number) => void }) {
  const dragging = useRef(false);
  const lastY = useRef(0);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    lastY.current = e.clientY;

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragging.current) return;
      const delta = lastY.current - ev.clientY;
      lastY.current = ev.clientY;
      onResize(delta);
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
      className="absolute top-0 left-0 right-0 h-1 cursor-row-resize z-10 hover:bg-info/30 active:bg-info/50 transition-colors"
    />
  );
}

export function ConsolePanel({ logs, runStatus, error }: ConsolePanelProps) {
  const [open, setOpen] = useState(true);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleResize = useCallback((delta: number) => {
    setHeight((h) => Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, h + delta)));
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 border-t border-white/[0.06] bg-[rgb(10_11_13)] px-4 py-1.5 text-[11px] text-fg-muted hover:text-fg-primary transition-colors w-full"
      >
        <ChevronUp size={12} />
        Console
        {runStatus !== "idle" && (
          <span className={cn("ml-1 font-medium", STATUS_COLORS[runStatus])}>
            {runStatus}
          </span>
        )}
        {logs.length > 0 && (
          <span className="ml-auto text-fg-disabled">{logs.length} events</span>
        )}
      </button>
    );
  }

  return (
    <div className="relative flex flex-col border-t border-white/[0.06] bg-[rgb(10_11_13)]" style={{ height }}>
      <ResizeHandle onResize={handleResize} />

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-white/[0.06]">
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-medium text-fg-muted">Console</span>
          {runStatus !== "idle" && (
            <span className={cn("text-[11px] font-medium", STATUS_COLORS[runStatus])}>
              {runStatus}
            </span>
          )}
          {logs.length > 0 && (
            <span className="text-[10px] text-fg-disabled">{logs.length} events</span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="p-0.5 text-fg-disabled hover:text-fg-muted transition-colors"
        >
          <ChevronDown size={12} />
        </button>
      </div>

      {/* Log body */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-2 font-mono text-[11px] leading-relaxed">
        {logs.length === 0 && runStatus === "idle" && (
          <p className="text-fg-disabled">Run a workflow to see execution logs.</p>
        )}
        {logs.length === 0 && runStatus === "running" && (
          <p className="text-fg-disabled">Waiting for events…</p>
        )}
        {logs.map((entry, i) => (
          <div key={i} className="flex gap-2 py-0.5">
            <span className="shrink-0 text-fg-disabled w-16 text-right">
              {entry.node_id.split("_").slice(0, -1).join("_")}
            </span>
            <LogContent entry={entry} />
          </div>
        ))}
        {error && (
          <div className="py-1 text-danger">{error}</div>
        )}
        {runStatus === "completed" && (
          <div className="py-1 text-success">Run completed.</div>
        )}
      </div>
    </div>
  );
}

function LogContent({ entry }: { entry: NodeLogEntry }) {
  switch (entry.log_type) {
    case "chunk":
      return <span className="text-fg-secondary">{entry.content}</span>;
    case "thinking":
      return <span className="text-fg-disabled italic">{entry.content}</span>;
    case "tool_use":
      return (
        <span className="text-warning">
          tool: {entry.name}
        </span>
      );
    case "tool_result":
      return (
        <span className="text-fg-muted">
          result: {(entry.content ?? "").slice(0, 200)}
        </span>
      );
    default:
      return <span className="text-fg-muted">{JSON.stringify(entry)}</span>;
  }
}
