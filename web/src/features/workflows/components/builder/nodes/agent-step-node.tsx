"use client";

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { Bot } from "@/components/icons";
import { BaseNode } from "./base-node";
import type { AgentStepData } from "@/features/workflows/lib/types";

export const AgentStepNode = memo(function AgentStepNode({
  data,
  selected,
}: NodeProps) {
  const d = data as AgentStepData;
  return (
    <BaseNode
      label={d.label}
      icon={<Bot size={14} strokeWidth={1.75} />}
      accent="border-brand/30"
      selected={selected}
    >
      {d.instruction && (
        <p className="type-caption text-fg-muted line-clamp-2">{d.instruction}</p>
      )}
    </BaseNode>
  );
});
