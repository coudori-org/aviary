"use client";

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { GitBranch, Layers } from "@/components/icons";
import { BaseNode } from "./base-node";
import type { ConditionData, MergeData } from "@/features/workflows/lib/types";

const CONDITION_COLOR = "#ffbc33";
const MERGE_COLOR = "#b48eff";

export const ConditionNode = memo(function ConditionNode({
  data,
  selected,
}: NodeProps) {
  const d = data as ConditionData;
  return (
    <BaseNode
      label={d.label}
      icon={<GitBranch size={14} strokeWidth={1.75} />}
      color={CONDITION_COLOR}
      selected={selected}
      outputs={2}
      outputLabels={["True", "False"]}
    >
      {d.expression && (
        <p className="text-[11px] text-fg-disabled truncate font-mono">{d.expression}</p>
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
      color={MERGE_COLOR}
      selected={selected}
      compact
    />
  );
});
