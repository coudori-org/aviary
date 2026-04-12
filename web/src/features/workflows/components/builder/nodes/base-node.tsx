"use client";

import { Handle, Position } from "@xyflow/react";
import { cn } from "@/lib/utils";

interface BaseNodeProps {
  label: string;
  icon: React.ReactNode;
  accent?: string;
  selected?: boolean;
  inputs?: number;
  outputs?: number;
  outputLabels?: string[];
  children?: React.ReactNode;
}

export function BaseNode({
  label,
  icon,
  accent = "border-white/10",
  selected,
  inputs = 1,
  outputs = 1,
  outputLabels,
  children,
}: BaseNodeProps) {
  return (
    <div
      className={cn(
        "relative min-w-[180px] rounded-lg border bg-elevated shadow-2 transition-shadow",
        selected ? "ring-2 ring-brand/50 border-brand/30" : accent,
      )}
    >
      {/* Input handles */}
      {Array.from({ length: inputs }).map((_, i) => (
        <Handle
          key={`in-${i}`}
          type="target"
          position={Position.Top}
          id={`in-${i}`}
          className="!w-2.5 !h-2.5 !bg-fg-muted !border-elevated"
        />
      ))}

      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.06]">
        <span className="text-fg-secondary">{icon}</span>
        <span className="type-caption-bold text-fg-primary truncate">{label}</span>
      </div>

      {/* Body */}
      {children && <div className="px-3 py-2">{children}</div>}

      {/* Output handles */}
      {Array.from({ length: outputs }).map((_, i) => (
        <Handle
          key={`out-${i}`}
          type="source"
          position={Position.Bottom}
          id={`out-${i}`}
          className="!w-2.5 !h-2.5 !bg-brand !border-elevated"
          style={
            outputs > 1
              ? { left: `${((i + 1) / (outputs + 1)) * 100}%` }
              : undefined
          }
        />
      ))}

      {/* Output labels */}
      {outputLabels && (
        <div className="flex justify-around px-1 pb-1">
          {outputLabels.map((lbl) => (
            <span key={lbl} className="type-caption text-fg-disabled text-[10px]">
              {lbl}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
