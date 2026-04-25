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
    running: { icon: <Loader2 size={10} className="animate-spin" />, bg: "bg-accent-soft", ring: "ring-accent-border", fg: "text-accent" },
    completed: { icon: <Check size={10} strokeWidth={3} />, bg: "bg-status-live-soft", ring: "ring-status-live/40", fg: "text-status-live" },
    failed: { icon: <X size={10} strokeWidth={3} />, bg: "bg-status-error-soft", ring: "ring-status-error/40", fg: "text-status-error" },
    skipped: { icon: <CircleDot size={10} />, bg: "bg-hover", ring: "ring-border-subtle", fg: "text-fg-muted" },
  }[status];

  if (!config) return null;

  return (
    <div className={cn("absolute -top-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full ring-1", config.bg, config.ring)}>
      <span className={config.fg}>
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
        "relative rounded-[10px] transition-all duration-200 ease-out",
        compact ? "min-w-[140px] max-w-[180px]" : "min-w-[200px] max-w-[260px]",
        "bg-raised border border-border-subtle",
        selected && "ring-2 ring-accent ring-offset-2 ring-offset-canvas",
        isRunning && "border-accent-border",
      )}
      style={{
        boxShadow: isRunning
          ? "0 0 24px var(--accent-blue-soft), var(--shadow-md)"
          : selected
            ? "0 0 0 1px var(--accent-blue-border), var(--shadow-lg)"
            : "var(--shadow-sm)",
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
            <span key={lbl} className="translate-x-full pl-2.5 text-[10px] font-medium text-fg-muted">
              {lbl}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
