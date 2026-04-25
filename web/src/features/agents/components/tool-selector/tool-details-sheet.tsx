"use client";

import { useEffect } from "react";
import { Lock, Server, Wrench, X } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { McpToolInfo } from "@/types";
import { extractToolParams, type ToolParam } from "./tool-params";

interface ToolDetailsSheetProps {
  tool: McpToolInfo | null;
  onClose: () => void;
}

/**
 * ToolDetailsSheet — centered modal that shows the full spec of a single
 * MCP tool: complete description (no truncation), every parameter with
 * type / required flag / docstring, and a clear marker for parameters
 * that are auto-injected from a Vault credential by the MCP gateway.
 *
 * Stacks above the ToolSelector modal (z-60 vs z-50) so it can be opened
 * from a tool card without losing the underlying selection state.
 *
 * Closes on backdrop click, X button, or Escape key.
 */
export function ToolDetailsSheet({ tool, onClose }: ToolDetailsSheetProps) {
  useEffect(() => {
    if (!tool) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tool, onClose]);

  if (!tool) return null;

  const params = extractToolParams(tool.input_schema);
  const requiredParams = params.filter((p) => p.required && !p.vaultKey);
  const optionalParams = params.filter((p) => !p.required && !p.vaultKey);
  const injectedParams = params.filter((p) => p.vaultKey);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-overlay backdrop-blur-sm animate-fade-in-fast p-6"
      onClick={onClose}
    >
      <div
        className="flex h-full max-h-[80vh] w-full max-w-2xl flex-col rounded-xl bg-popover border border-border shadow-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-6 py-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Wrench size={14} strokeWidth={1.75} className="shrink-0 text-fg-muted" />
              <span className="truncate font-mono type-button text-fg-primary">
                {tool.qualified_name}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-1.5 type-caption text-fg-muted">
              <Server size={11} strokeWidth={1.75} />
              <span>{tool.server_name}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-fg-muted hover:text-fg-primary transition-colors"
            aria-label="Close"
          >
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {tool.description && (
            <section>
              <SectionLabel>Description</SectionLabel>
              <p className="mt-1.5 type-caption text-fg-secondary whitespace-pre-wrap leading-relaxed">
                {tool.description}
              </p>
            </section>
          )}

          {requiredParams.length > 0 && (
            <ParamSection label="Required parameters" params={requiredParams} />
          )}
          {optionalParams.length > 0 && (
            <ParamSection label="Optional parameters" params={optionalParams} />
          )}
          {injectedParams.length > 0 && (
            <ParamSection
              label="Auto-filled from Vault"
              params={injectedParams}
              footnote="These parameters are filled by the MCP gateway from your Vault credentials before the tool is called. The agent never sees them — they exist here just so you know which credentials to set up."
            />
          )}

          {params.length === 0 && (
            <p className="type-caption text-fg-muted">
              This tool takes no parameters.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="type-small font-semibold uppercase tracking-wide text-fg-muted">
      {children}
    </h3>
  );
}

function ParamSection({
  label,
  params,
  footnote,
}: {
  label: string;
  params: ToolParam[];
  footnote?: string;
}) {
  return (
    <section>
      <SectionLabel>{label}</SectionLabel>
      {footnote && (
        <p className="mt-1.5 type-caption text-fg-muted leading-relaxed">{footnote}</p>
      )}
      <ul className="mt-2 space-y-2">
        {params.map((p) => (
          <ParamRow key={p.name} param={p} />
        ))}
      </ul>
    </section>
  );
}

function ParamRow({ param }: { param: ToolParam }) {
  const injected = !!param.vaultKey;
  return (
    <li
      className={cn(
        "rounded-md border px-3 py-2",
        injected
          ? "border-info/30 bg-info/[0.08]"
          : "border-border bg-raised",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono type-caption text-fg-primary">{param.name}</span>
        <span className="font-mono text-[10px] text-fg-muted">{param.type}</span>
        {param.required && !injected && (
          <span className="rounded-xs bg-warning/15 px-1.5 py-px text-[10px] uppercase tracking-wide text-warning ring-1 ring-inset ring-warning/20">
            required
          </span>
        )}
        {injected && (
          <span
            title={`Auto-filled from your Vault credential: ${param.vaultKey}`}
            className="inline-flex items-center gap-1 rounded-xs bg-info/10 px-1.5 py-px font-mono text-[10px] text-info ring-1 ring-inset ring-info/20"
          >
            <Lock size={9} strokeWidth={2.25} />
            {param.vaultKey}
          </span>
        )}
      </div>
      {param.description && (
        <p className="mt-1 type-caption text-fg-secondary whitespace-pre-wrap leading-relaxed">
          {param.description}
        </p>
      )}
      {param.defaultValue !== undefined && (
        <p className="mt-1 font-mono text-[10px] text-fg-muted">
          default: {JSON.stringify(param.defaultValue)}
        </p>
      )}
    </li>
  );
}
