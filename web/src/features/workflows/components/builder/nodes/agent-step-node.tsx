"use client";

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { Bot } from "@/components/icons";
import { BaseNode } from "./base-node";
import type { AgentStepData } from "@/features/workflows/lib/types";

const AGENT_COLOR = "#55b3ff";

export const AgentStepNode = memo(function AgentStepNode({
  data,
  selected,
}: NodeProps) {
  const d = data as AgentStepData;
  return (
    <BaseNode
      label={d.label}
      icon={<Bot size={14} strokeWidth={1.75} />}
      color={AGENT_COLOR}
      selected={selected}
    >
      {d.instruction && (
        <p className="text-[11px] text-fg-muted line-clamp-2 leading-relaxed">{d.instruction}</p>
      )}
    </BaseNode>
  );
});
