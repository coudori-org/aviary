"use client";

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { Play, Globe } from "@/components/icons";
import { BaseNode } from "./base-node";
import type { ManualTriggerData, WebhookTriggerData } from "@/features/workflows/lib/types";

const TRIGGER_COLOR = "#5fc992";

export const ManualTriggerNode = memo(function ManualTriggerNode({
  data,
  selected,
}: NodeProps) {
  const d = data as ManualTriggerData;
  return (
    <BaseNode
      label={d.label}
      icon={<Play size={14} strokeWidth={2} />}
      color={TRIGGER_COLOR}
      selected={selected}
      compact
      inputs={0}
      outputs={1}
    />
  );
});

export const WebhookTriggerNode = memo(function WebhookTriggerNode({
  data,
  selected,
}: NodeProps) {
  const d = data as WebhookTriggerData;
  return (
    <BaseNode
      label={d.label}
      icon={<Globe size={14} strokeWidth={1.75} />}
      color={TRIGGER_COLOR}
      selected={selected}
      inputs={0}
      outputs={1}
    >
      <p className="text-[11px] text-fg-muted font-mono truncate">{d.path}</p>
    </BaseNode>
  );
});
