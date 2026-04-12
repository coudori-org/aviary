"use client";

import { Handle, Position, useNodeId } from "@xyflow/react";
import { Loader2, Check, X, CircleDot } from "@/components/icons";
import { cn } from "@/lib/utils";
import { useNodeRunStatus } from "@/features/workflows/providers/run-status-provider";

interface BaseNodeProps {
  label: string;
  icon: React.ReactNode;
  color: string;
  selected?: boolean;
  compact?: boolean;
  inputs?: number;
  outputs?: number;
  outputLabels?: string[];
  children?: React.ReactNode;
}

function RunStatusBadge() {
  const nodeId = useNodeId();
  const status = useNodeRunStatus(nodeId ?? "");

  if (!status || status === "pending") return null;

  const config = {
    running: { icon: <Loader2 size={10} className="animate-spin" />, bg: "bg-info/20", ring: "ring-info/30" },
    completed: { icon: <Check size={10} strokeWidth={3} />, bg: "bg-success/20", ring: "ring-success/30" },
    failed: { icon: <X size={10} strokeWidth={3} />, bg: "bg-danger/20", ring: "ring-danger/30" },
    skipped: { icon: <CircleDot size={10} />, bg: "bg-white/5", ring: "ring-white/10" },
  }[status];

  if (!config) return null;

  return (
    <div className={cn("absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full ring-1", config.bg, config.ring)}>
      <span className={status === "completed" ? "text-success" : status === "failed" ? "text-danger" : status === "running" ? "text-info" : "text-fg-disabled"}>
        {config.icon}
      </span>
    </div>
  );
}

export function BaseNode({
  label,
  icon,
  color,
  selected,
  compact,
  inputs = 1,
  outputs = 1,
  outputLabels,
  children,
}: BaseNodeProps) {
  const nodeId = useNodeId();
  const runStatus = useNodeRunStatus(nodeId ?? "");
  const isRunning = runStatus === "running";

  return (
    <div
      className={cn(
        "relative rounded-lg transition-all duration-150",
        compact ? "min-w-[140px] max-w-[180px]" : "min-w-[200px] max-w-[260px]",
        "bg-[rgb(16_17_17)] border border-white/[0.06]",
        selected && "ring-1 ring-info/50 border-info/30",
        isRunning && "border-info/20",
      )}
      style={{
        boxShadow: isRunning
          ? "0 0 20px rgba(85,179,255,0.1), 0 4px 12px rgba(0,0,0,0.3)"
          : selected
            ? "0 0 16px rgba(85,179,255,0.08), 0 4px 12px rgba(0,0,0,0.3)"
            : "0 2px 8px rgba(0,0,0,0.3)",
      }}
    >
      <RunStatusBadge />

      {/* Input handles */}
      {Array.from({ length: inputs }).map((_, i) => (
        <Handle
          key={`in-${i}`}
          type="target"
          position={Position.Left}
          id={`in-${i}`}
          style={inputs > 1 ? { top: `${((i + 1) / (inputs + 1)) * 100}%` } : undefined}
        />
      ))}

      {/* Header */}
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <div
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md"
          style={{ backgroundColor: `${color}15`, color }}
        >
          {icon}
        </div>
        <span className="text-[13px] font-medium text-fg-primary truncate leading-tight">
          {label}
        </span>
      </div>

      {/* Body */}
      {children && (
        <div className="px-3 pb-2.5 -mt-0.5">
          {children}
        </div>
      )}

      {/* Output handles */}
      {Array.from({ length: outputs }).map((_, i) => (
        <Handle
          key={`out-${i}`}
          type="source"
          position={Position.Right}
          id={`out-${i}`}
          style={outputs > 1 ? { top: `${((i + 1) / (outputs + 1)) * 100}%` } : undefined}
        />
      ))}

      {/* Output labels */}
      {outputLabels && outputs > 1 && (
        <div className="absolute -right-1 top-0 h-full flex flex-col justify-around py-3 pointer-events-none">
          {outputLabels.map((lbl) => (
            <span key={lbl} className="translate-x-full pl-2.5 text-[10px] font-medium text-fg-disabled">
              {lbl}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
