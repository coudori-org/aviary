"use client";

import { Check, Wrench } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { McpToolInfo } from "@/types";

interface ToolCardProps {
  tool: McpToolInfo;
  checked: boolean;
  onToggle: (id: string) => void;
}

/**
 * ToolCard — card-style MCP tool picker item. Clicking anywhere
 * toggles selection; the checked state is conveyed by a filled circle
 * on the top-right and a tinted border.
 */
export function ToolCard({ tool, checked, onToggle }: ToolCardProps) {
  const inputKeys = extractInputKeys(tool.input_schema);

  return (
    <button
      type="button"
      onClick={() => onToggle(tool.id)}
      className={cn(
        "group relative flex flex-col items-start gap-1.5 rounded-md border px-3 py-2.5 text-left transition-colors",
        checked
          ? "border-info/50 bg-info/[0.05]"
          : "border-white/[0.06] bg-raised/30 hover:border-white/[0.12] hover:bg-raised/60",
      )}
    >
      <div className="flex w-full items-center gap-2">
        <Wrench size={12} strokeWidth={1.75} className="shrink-0 text-fg-muted" />
        <span className="flex-1 truncate font-mono type-caption text-fg-primary">
          {tool.name}
        </span>
        <span
          className={cn(
            "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors",
            checked
              ? "border-info bg-info text-canvas"
              : "border-white/20 bg-transparent",
          )}
          aria-hidden="true"
        >
          {checked && <Check size={10} strokeWidth={3} />}
        </span>
      </div>

      {tool.description && (
        <p className="line-clamp-2 type-caption text-fg-muted">{tool.description}</p>
      )}

      {inputKeys.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {inputKeys.slice(0, 5).map((key) => (
            <span
              key={key}
              className="rounded-xs bg-white/[0.04] px-1.5 py-px font-mono text-[10px] text-fg-disabled"
            >
              {key}
            </span>
          ))}
          {inputKeys.length > 5 && (
            <span className="font-mono text-[10px] text-fg-disabled">
              +{inputKeys.length - 5}
            </span>
          )}
        </div>
      )}
    </button>
  );
}

/** Returns the top-level property names from a JSON Schema object, or
 *  an empty array if the schema isn't shaped like `{ properties: {...} }`. */
function extractInputKeys(schema: Record<string, unknown>): string[] {
  const props = schema?.properties;
  if (!props || typeof props !== "object") return [];
  return Object.keys(props as Record<string, unknown>);
}
