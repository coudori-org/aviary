"use client";

import { Wrench, X } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { McpToolInfo } from "@/types";

interface ToolChipProps {
  id: string;
  info: McpToolInfo | undefined;
  onRemove: (id: string) => void;
  onShowDetails: (info: McpToolInfo) => void;
}

/**
 * Selected-tool chip for the agent form. Click the label to open the full
 * details sheet (description + every parameter, including the vault-key
 * annotations). Click the X to remove the binding.
 */
export function ToolChip({ id, info, onRemove, onShowDetails }: ToolChipProps) {
  const label = info?.qualified_name || id;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[5px]",
        "bg-accent-soft text-accent border border-accent-border"
      )}
    >
      <button
        type="button"
        disabled={!info}
        onClick={() => info && onShowDetails(info)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-l-[5px] py-1 pl-2 pr-1",
          "t-mono text-[11.5px] transition-colors duration-fast",
          "enabled:hover:bg-accent/10 enabled:cursor-pointer disabled:cursor-default"
        )}
        title={info ? "View tool details" : undefined}
      >
        <Wrench size={11} strokeWidth={2} />
        <span>{label}</span>
      </button>
      <button
        type="button"
        onClick={() => onRemove(id)}
        className={cn(
          "rounded-r-[5px] py-1 pl-0.5 pr-2 transition-colors duration-fast",
          "text-accent/70 hover:bg-accent/10 hover:text-accent"
        )}
        aria-label={`Remove ${label}`}
      >
        <X size={10} strokeWidth={2.5} />
      </button>
    </span>
  );
}
