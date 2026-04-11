"use client";

import { Wrench, X } from "@/components/icons";
import type { McpToolInfo } from "@/types";

interface ToolChipProps {
  id: string;
  info: McpToolInfo | undefined;
  onRemove: (id: string) => void;
}

/**
 * ToolChip — selected-tool chip for the agent form with a hover popover
 * that previews the tool's description and input schema. Falls back to
 * a plain chip when only the id is known (e.g. before the tool map has
 * hydrated from the MCP API).
 */
export function ToolChip({ id, info, onRemove }: ToolChipProps) {
  const label = info?.qualified_name || id.slice(0, 8);
  const inputKeys = info ? extractInputKeys(info.input_schema) : [];

  return (
    <span className="group/chip relative inline-flex items-center gap-1.5 rounded-sm bg-info/10 px-2.5 py-1 type-caption text-info ring-1 ring-inset ring-info/20">
      <Wrench size={11} strokeWidth={2} />
      <span className="font-mono">{label}</span>
      <button
        type="button"
        onClick={() => onRemove(id)}
        className="ml-0.5 text-info/60 hover:text-info"
        aria-label={`Remove ${label}`}
      >
        <X size={10} strokeWidth={2.5} />
      </button>

      {info && (info.description || inputKeys.length > 0) && (
        <div className="pointer-events-none absolute left-0 top-full z-20 mt-1 hidden w-72 rounded-md border border-white/[0.08] bg-elevated p-3 shadow-4 group-hover/chip:block">
          <div className="mb-1 font-mono type-caption text-fg-primary">
            {info.qualified_name}
          </div>
          {info.description && (
            <p className="type-caption text-fg-muted whitespace-normal leading-relaxed">
              {info.description}
            </p>
          )}
          {inputKeys.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {inputKeys.map((key) => (
                <span
                  key={key}
                  className="rounded-xs bg-white/[0.04] px-1.5 py-px font-mono text-[10px] text-fg-disabled"
                >
                  {key}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </span>
  );
}

function extractInputKeys(schema: Record<string, unknown>): string[] {
  const props = schema?.properties;
  if (!props || typeof props !== "object") return [];
  return Object.keys(props as Record<string, unknown>);
}
