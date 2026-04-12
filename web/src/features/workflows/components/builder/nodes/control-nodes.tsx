"use client";

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { GitBranch, Layers } from "@/components/icons";
import { BaseNode } from "./base-node";
import type { ConditionData, MergeData } from "@/features/workflows/lib/types";

export const ConditionNode = memo(function ConditionNode({
  data,
  selected,
}: NodeProps) {
  const d = data as ConditionData;
  return (
    <BaseNode
      label={d.label}
      icon={<GitBranch size={14} strokeWidth={1.75} />}
      accent="border-warning/30"
      selected={selected}
      outputs={2}
      outputLabels={["True", "False"]}
    >
      {d.expression && (
        <p className="type-caption text-fg-muted truncate font-mono">{d.expression}</p>
      )}
    </BaseNode>
  );
});

export const MergeNode = memo(function MergeNode({
  data,
  selected,
}: NodeProps) {
  const d = data as MergeData;
  return (
    <BaseNode
      label={d.label}
      icon={<Layers size={14} strokeWidth={1.75} />}
      accent="border-info/30"
      selected={selected}
    />
  );
});
