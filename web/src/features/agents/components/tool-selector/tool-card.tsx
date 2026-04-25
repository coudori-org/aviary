"use client";

import { Check, Info, Lock, Wrench } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { McpToolInfo } from "@/types";
import { extractToolParams, type ToolParam } from "./tool-params";

interface ToolCardProps {
  tool: McpToolInfo;
  checked: boolean;
  onToggle: (id: string) => void;
  onShowDetails: (tool: McpToolInfo) => void;
}

const MAX_VISIBLE_PARAMS = 5;

/**
 * ToolCard — card-style MCP tool picker item. Clicking anywhere
 * toggles selection; the checked state is conveyed by a filled circle
 * on the top-right and a tinted border. The (i) button on hover opens
 * the full details sheet without affecting selection. Vault-injected
 * parameters are marked with a lock icon and a tooltip showing the
 * source Vault key.
 */
export function ToolCard({ tool, checked, onToggle, onShowDetails }: ToolCardProps) {
  const params = extractToolParams(tool.input_schema);
  const visible = params.slice(0, MAX_VISIBLE_PARAMS);
  const overflow = params.length - visible.length;

  return (
    <button
      type="button"
      onClick={() => onToggle(tool.id)}
      className={cn(
        "group relative flex flex-col items-start gap-1.5 rounded-md border px-3 py-2.5 text-left transition-colors",
        checked
          ? "border-info/60 bg-info/[0.10] hover:bg-info/[0.14]"
          : "border-border bg-raised hover:border-border-strong hover:bg-hover",
      )}
    >
      <div className="flex w-full items-center gap-2">
        <Wrench size={12} strokeWidth={1.75} className="shrink-0 text-fg-secondary" />
        <span className="flex-1 truncate font-mono type-caption text-fg-primary">
          {tool.name}
        </span>
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            onShowDetails(tool);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              onShowDetails(tool);
            }
          }}
          className="flex h-4 w-4 shrink-0 items-center justify-center rounded-xs text-fg-disabled opacity-0 transition-opacity hover:text-info group-hover:opacity-100 focus:opacity-100"
          title="View details"
          aria-label="View tool details"
        >
          <Info size={12} strokeWidth={1.75} />
        </span>
        <span
          className={cn(
            "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors",
            checked
              ? "border-info bg-info text-canvas"
              : "border-border-strong bg-canvas/40",
          )}
          aria-hidden="true"
        >
          {checked && <Check size={10} strokeWidth={3} />}
        </span>
      </div>

      {tool.description && (
        <p className="line-clamp-2 type-caption text-fg-muted">{tool.description}</p>
      )}

      {params.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {visible.map((p) => (
            <ParamTag key={p.name} param={p} />
          ))}
          {overflow > 0 && (
            <span className="font-mono text-[10px] text-fg-muted">+{overflow}</span>
          )}
        </div>
      )}
    </button>
  );
}

/**
 * Single parameter chip. Vault-injected params get a lock icon, an info-
 * tinted background, and a `title` tooltip naming the source Vault key so
 * users know which credential they need to set up before using the tool.
 */
function ParamTag({ param }: { param: ToolParam }) {
  if (param.vaultKey) {
    return (
      <span
        title={`Auto-filled from your Vault credential: ${param.vaultKey}`}
        className="inline-flex items-center gap-1 rounded-xs bg-info/10 px-1.5 py-px font-mono text-[10px] text-info ring-1 ring-inset ring-info/20"
      >
        <Lock size={8} strokeWidth={2.25} />
        {param.name}
      </span>
    );
  }
  return (
    <span className="rounded-xs bg-active px-1.5 py-px font-mono text-[10px] text-fg-primary ring-1 ring-inset ring-border-strong">
      {param.name}
    </span>
  );
}
