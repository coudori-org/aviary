"use client";

import { useState, useEffect, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plus } from "@/components/icons";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { ModelSelect } from "./model-select";
import { ToolSelector } from "@/features/agents/components/tool-selector/tool-selector";
import { ToolDetailsSheet } from "@/features/agents/components/tool-selector/tool-details-sheet";
import { ToolChip } from "@/features/agents/components/form/tool-chip";
import type { WorkflowNode } from "@/features/workflows/lib/types";
import type { McpToolInfo } from "@/types";

function NodeField({
  id,
  label,
  value,
  onCommit,
  multiline,
  placeholder,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onCommit: (value: string) => void;
  multiline?: boolean;
  placeholder?: string;
  hint?: string;
}) {
  const [local, setLocal] = useState(value);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setLocal(value);
  }, [value, focused]);

  const handleBlur = () => {
    setFocused(false);
    if (local !== value) onCommit(local);
  };

  const Component = multiline ? Textarea : Input;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
        {label}
      </Label>
      <Component
        id={id}
        value={local}
        onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setLocal(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={handleBlur}
        placeholder={placeholder}
        className="text-[13px]"
        {...(multiline ? { rows: 4 } : {})}
      />
      {hint && <p className="text-[10px] text-fg-disabled">{hint}</p>}
    </div>
  );
}

function NodeNumberField({
  id, label, value, min, max, onCommit, hint,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  onCommit: (value: number) => void;
  hint?: string;
}) {
  const [local, setLocal] = useState(String(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setLocal(String(value));
  }, [value, focused]);

  const handleBlur = () => {
    setFocused(false);
    const parsed = parseInt(local, 10);
    const next = Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : value;
    setLocal(String(next));
    if (next !== value) onCommit(next);
  };

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={handleBlur}
        className="text-[13px]"
      />
      {hint && <p className="text-[10px] text-fg-disabled">{hint}</p>}
    </div>
  );
}

const TRIGGER_NODE_TYPES = new Set(["manual_trigger", "webhook_trigger"]);

function ToolsField({
  toolIds,
  onChange,
}: {
  toolIds: string[];
  onChange: (next: string[]) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [detailsTool, setDetailsTool] = useState<McpToolInfo | null>(null);
  const [toolInfoMap, setToolInfoMap] = useState<Map<string, McpToolInfo>>(new Map());

  const removeTool = useCallback(
    (id: string) => onChange(toolIds.filter((t) => t !== id)),
    [toolIds, onChange],
  );

  return (
    <div className="space-y-2">
      <Label className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
        Tools
      </Label>

      {toolIds.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {toolIds.map((id) => (
            <ToolChip
              key={id}
              id={id}
              info={toolInfoMap.get(id)}
              onRemove={removeTool}
              onShowDetails={setDetailsTool}
            />
          ))}
        </div>
      ) : (
        <p className="text-[11px] text-fg-disabled">No tools connected.</p>
      )}

      <button
        type="button"
        onClick={() => setPickerOpen(true)}
        className="inline-flex items-center gap-1 rounded-sm border border-white/[0.08] bg-transparent px-2 py-1 text-[11px] text-fg-muted hover:bg-white/[0.04] hover:text-fg-primary transition-colors"
      >
        <Plus size={11} strokeWidth={2.25} />
        Add tools
      </button>

      <ToolSelector
        selectedToolIds={toolIds}
        onChange={(ids, map) => {
          onChange(ids);
          if (map) setToolInfoMap(map);
        }}
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
      />

      <ToolDetailsSheet tool={detailsTool} onClose={() => setDetailsTool(null)} />
    </div>
  );
}

export function InspectorPanel() {
  const { nodes, selectedNodeId, updateNodeData } = useWorkflowBuilder();

  const node = selectedNodeId
    ? (nodes.find((n) => n.id === selectedNodeId) as WorkflowNode | undefined)
    : null;

  if (!node) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <p className="text-center text-[12px] text-fg-disabled leading-relaxed">
          Select a node to<br />view its properties
        </p>
      </div>
    );
  }

  const d = node.data as Record<string, unknown>;
  const commit = (key: string) => (value: string) => updateNodeData(node.id, key, value);

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex flex-col gap-4 px-4 py-4">
        <NodeField
          id="node-label"
          label="Label"
          value={(d.label as string) ?? ""}
          onCommit={commit("label")}
        />

        {node.type === "agent_step" && (
          <>
            <ModelSelect
              backend={(d.model_config as Record<string, string>)?.backend ?? ""}
              model={(d.model_config as Record<string, string>)?.model ?? ""}
              onChange={(backend, model) =>
                updateNodeData(node.id, "model_config", { ...d.model_config as object, backend, model })
              }
            />
            <NodeField
              id="node-instruction"
              label="Instruction"
              value={(d.instruction as string) ?? ""}
              onCommit={commit("instruction")}
              multiline
              placeholder="System prompt for this step"
            />
            <NodeField
              id="node-prompt-template"
              label="Prompt Template"
              value={(d.prompt_template as string) ?? ""}
              onCommit={commit("prompt_template")}
              multiline
              placeholder="{{input}}"
              hint="Use {{input}} for upstream data"
            />
            <ToolsField
              toolIds={(d.mcp_tool_ids as string[]) ?? []}
              onChange={(next) => updateNodeData(node.id, "mcp_tool_ids", next)}
            />
          </>
        )}

        {node.type === "condition" && (
          <NodeField
            id="node-expression"
            label="Expression"
            value={(d.expression as string) ?? ""}
            onCommit={commit("expression")}
            placeholder='output.contains("yes")'
          />
        )}

        {node.type === "webhook_trigger" && (
          <NodeField
            id="node-path"
            label="Webhook Path"
            value={(d.path as string) ?? ""}
            onCommit={commit("path")}
            placeholder="/webhook"
          />
        )}

        {node.type === "template" && (
          <NodeField
            id="node-template"
            label="Template"
            value={(d.template as string) ?? ""}
            onCommit={commit("template")}
            multiline
            placeholder="Hello {{name}}"
          />
        )}

        {/* Execution — hidden for trigger nodes since they don't run an activity */}
        {!TRIGGER_NODE_TYPES.has(node.type) && (
          <div className="mt-2 space-y-3 border-t border-white/[0.06] pt-4">
            <NodeNumberField
              id="node-retry-count"
              label="Retry count"
              value={typeof d.retry_count === "number" ? d.retry_count : 1}
              min={1}
              max={10}
              onCommit={(v) => updateNodeData(node.id, "retry_count", v)}
              hint="Max attempts (1 = no retry). Default 1."
            />
          </div>
        )}

        {/* Meta */}
        <div className="mt-2 space-y-1 border-t border-white/[0.06] pt-4">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-fg-disabled">Type</span>
            <span className="text-[11px] text-fg-muted">{node.type}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-fg-disabled">ID</span>
            <span className="text-[10px] text-fg-disabled font-mono truncate max-w-[120px]">{node.id}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
