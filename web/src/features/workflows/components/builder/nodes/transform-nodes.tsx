"use client";

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { Filter, FileText } from "@/components/icons";
import { BaseNode } from "./base-node";
import type { PayloadParserData, TemplateData } from "@/features/workflows/lib/types";

const TRANSFORM_COLOR = "#e085d0";

export const PayloadParserNode = memo(function PayloadParserNode({
  data,
  selected,
}: NodeProps) {
  const d = data as PayloadParserData;
  const fieldCount = Object.keys(d.mapping ?? {}).length;
  return (
    <BaseNode
      label={d.label}
      icon={<Filter size={14} strokeWidth={1.75} />}
      color={TRANSFORM_COLOR}
      selected={selected}
    >
      <p className="text-[11px] text-fg-disabled">
        {fieldCount > 0 ? `${fieldCount} field${fieldCount !== 1 ? "s" : ""}` : "No mappings"}
      </p>
    </BaseNode>
  );
});

export const TemplateNode = memo(function TemplateNode({
  data,
  selected,
}: NodeProps) {
  const d = data as TemplateData;
  return (
    <BaseNode
      label={d.label}
      icon={<FileText size={14} strokeWidth={1.75} />}
      color={TRANSFORM_COLOR}
      selected={selected}
    >
      {d.template && (
        <p className="text-[11px] text-fg-disabled truncate font-mono">{d.template}</p>
      )}
    </BaseNode>
  );
});
