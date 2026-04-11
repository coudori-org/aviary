"use client";

import { Wrench, X } from "@/components/icons";
import type { McpToolInfo } from "@/types";

interface ToolChipProps {
  id: string;
  info: McpToolInfo | undefined;
  onRemove: (id: string) => void;
  onShowDetails: (info: McpToolInfo) => void;
}

/**
 * ToolChip — selected-tool chip for the agent form. Click the label to
 * open the full details sheet (description + every parameter, including
 * the vault-key annotations). Click the X to remove the binding. Falls
 * back to a non-clickable plain chip when only the id is known (e.g.
 * before the tool map has hydrated from the MCP API).
 */
export function ToolChip({ id, info, onRemove, onShowDetails }: ToolChipProps) {
  const label = info?.qualified_name || id.slice(0, 8);

  return (
    <span className="inline-flex items-center gap-1 rounded-sm bg-info/10 type-caption text-info ring-1 ring-inset ring-info/20">
      <button
        type="button"
        disabled={!info}
        onClick={() => info && onShowDetails(info)}
        className="inline-flex items-center gap-1.5 rounded-l-sm py-1 pl-2.5 pr-1 font-mono transition-colors enabled:hover:bg-info/[0.08] enabled:cursor-pointer disabled:cursor-default"
        title={info ? "View tool details" : undefined}
      >
        <Wrench size={11} strokeWidth={2} />
        <span>{label}</span>
      </button>
      <button
        type="button"
        onClick={() => onRemove(id)}
        className="rounded-r-sm py-1 pl-0.5 pr-2 text-info/60 transition-colors hover:bg-info/[0.08] hover:text-info"
        aria-label={`Remove ${label}`}
      >
        <X size={10} strokeWidth={2.5} />
      </button>
    </span>
  );
}
