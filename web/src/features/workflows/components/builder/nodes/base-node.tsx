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
    running: { icon: <Loader2 size={10} className="animate-spin" />, bg: "bg-aurora-violet/25", ring: "ring-aurora-violet/40" },
    completed: { icon: <Check size={10} strokeWidth={3} />, bg: "bg-aurora-mint/25", ring: "ring-aurora-mint/40" },
    failed: { icon: <X size={10} strokeWidth={3} />, bg: "bg-aurora-pink/25", ring: "ring-aurora-pink/40" },
    skipped: { icon: <CircleDot size={10} />, bg: "bg-white/5", ring: "ring-white/10" },
  }[status];

  if (!config) return null;

  return (
    <div className={cn("absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full ring-1", config.bg, config.ring)}>
      <span className={status === "completed" ? "text-aurora-mint" : status === "failed" ? "text-aurora-pink" : status === "running" ? "text-aurora-violet" : "text-fg-disabled"}>
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
        "relative rounded-lg transition-all duration-200 ease-out",
        compact ? "min-w-[140px] max-w-[180px]" : "min-w-[200px] max-w-[260px]",
        "glass-raised",
        selected && "ring-2 ring-aurora-violet ring-offset-2 ring-offset-[rgb(8_9_26)]",
        isRunning && "border-aurora-violet/40",
      )}
      style={{
        boxShadow: isRunning
          ? "0 0 28px rgba(123,92,255,0.35), 0 4px 16px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08)"
          : selected
            ? "0 0 40px rgba(123,92,255,0.7), 0 0 12px rgba(123,92,255,0.55), 0 4px 16px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1)"
            : "0 4px 16px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06)",
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
