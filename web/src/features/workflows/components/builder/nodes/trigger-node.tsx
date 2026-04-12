"use client";

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { Play, Globe } from "@/components/icons";
import { BaseNode } from "./base-node";
import type { ManualTriggerData, WebhookTriggerData } from "@/features/workflows/lib/types";

export const ManualTriggerNode = memo(function ManualTriggerNode({
  data,
  selected,
}: NodeProps) {
  const d = data as ManualTriggerData;
  return (
    <BaseNode
      label={d.label}
      icon={<Play size={14} strokeWidth={1.75} />}
      accent="border-success/30"
      selected={selected}
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
      accent="border-success/30"
      selected={selected}
      inputs={0}
      outputs={1}
    >
      <p className="type-caption text-fg-muted truncate">{d.path}</p>
    </BaseNode>
  );
});
