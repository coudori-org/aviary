"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Trash2, Lock } from "@/components/icons";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { ModelSelect } from "./model-select";
import { ToolSelector } from "@/features/agents/components/tool-selector/tool-selector";
import { ToolDetailsSheet } from "@/features/agents/components/tool-selector/tool-details-sheet";
import { ToolChip } from "@/features/agents/components/form/tool-chip";
import type { WorkflowNode, StructuredOutputField, ArtifactField } from "@/features/workflows/lib/types";
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

function OutputFieldRow({
  field, onChange, onRemove,
}: {
  field: StructuredOutputField;
  onChange: (patch: Partial<StructuredOutputField>) => void;
  onRemove: () => void;
}) {
  const [localName, setLocalName] = useState(field.name);
  const [localDesc, setLocalDesc] = useState(field.description ?? "");
  const nameFocused = useRef(false);
  const descFocused = useRef(false);

  useEffect(() => {
    if (!nameFocused.current) setLocalName(field.name);
  }, [field.name]);
  useEffect(() => {
    if (!descFocused.current) setLocalDesc(field.description ?? "");
  }, [field.description]);

  const commitName = () => {
    nameFocused.current = false;
    const trimmed = localName.trim();
    if (trimmed !== field.name) onChange({ name: trimmed });
    setLocalName(trimmed);
  };
  const commitDesc = () => {
    descFocused.current = false;
    const next = localDesc.trim();
    const prev = field.description ?? "";
    if (next !== prev) onChange({ description: next || undefined });
    setLocalDesc(next);
  };

  return (
    <div className="space-y-1.5 rounded-md border border-white/[0.08] bg-white/[0.02] px-2 py-2">
      <div className="flex items-center gap-1.5">
        <Input
          value={localName}
          placeholder="field_name"
          onChange={(e) => setLocalName(e.target.value)}
          onFocus={() => { nameFocused.current = true; }}
          onBlur={commitName}
          className="flex-1 h-7 text-[12px] font-mono"
        />
        <select
          value={field.type}
          onChange={(e) => onChange({ type: e.target.value as "str" | "list" })}
          className="h-7 rounded-md border border-white/[0.08] bg-canvas px-1.5 text-[12px] text-fg-primary focus:outline-none focus:border-info"
        >
          <option value="str">string</option>
          <option value="list">list</option>
        </select>
        <button
          type="button"
          onClick={onRemove}
          className="flex h-7 w-7 items-center justify-center rounded-md text-fg-disabled hover:bg-danger/10 hover:text-danger transition-colors"
          title="Remove field"
        >
          <Trash2 size={11} strokeWidth={1.75} />
        </button>
      </div>
      <Textarea
        value={localDesc}
        placeholder="Description (optional)"
        onChange={(e) => setLocalDesc(e.target.value)}
        onFocus={() => { descFocused.current = true; }}
        onBlur={commitDesc}
        rows={1}
        className="text-[12px]"
      />
    </div>
  );
}

function TextFieldRow({
  description, onChange,
}: {
  description: string;
  onChange: (next: string) => void;
}) {
  const [local, setLocal] = useState(description);
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setLocal(description);
  }, [description]);

  const commit = () => {
    focused.current = false;
    const next = local.trim();
    if (next !== description) onChange(next);
    setLocal(next);
  };

  return (
    <div className="space-y-1.5 rounded-md border border-white/[0.06] bg-white/[0.015] px-2 py-2">
      <div className="flex items-center gap-2">
        <Lock size={11} className="text-fg-disabled" strokeWidth={1.75} />
        <span className="text-[12px] font-mono text-fg-muted">text</span>
        <span className="text-[10px] text-fg-disabled">string</span>
        <span className="ml-auto text-[10px] text-fg-disabled">always included</span>
      </div>
      <Textarea
        value={local}
        placeholder="Description — guides how the agent summarizes its final answer (optional)"
        onChange={(e) => setLocal(e.target.value)}
        onFocus={() => { focused.current = true; }}
        onBlur={commit}
        rows={1}
        className="text-[12px]"
      />
    </div>
  );
}

function OutputFieldsEditor({
  fields, onChange,
}: {
  fields: StructuredOutputField[];
  onChange: (next: StructuredOutputField[]) => void;
}) {
  const textEntry = fields.find((f) => f.name === "text");
  const extras = fields.filter((f) => f.name !== "text");
  const textDescription = textEntry?.description ?? "";

  // Serialise back as `[text?, ...extras]`. The text entry leads whenever it
  // has a description; otherwise drop it to keep the stored data minimal.
  const emit = (nextTextDesc: string, nextExtras: StructuredOutputField[]) => {
    const out: StructuredOutputField[] = [];
    if (nextTextDesc) {
      out.push({ name: "text", type: "str", description: nextTextDesc });
    }
    out.push(...nextExtras);
    onChange(out);
  };

  const setTextDescription = (next: string) => emit(next, extras);
  const updateExtraAt = (idx: number, patch: Partial<StructuredOutputField>) =>
    emit(textDescription, extras.map((f, i) => (i === idx ? { ...f, ...patch } : f)));
  const removeExtraAt = (idx: number) =>
    emit(textDescription, extras.filter((_, i) => i !== idx));
  const addExtra = () =>
    emit(textDescription, [...extras, { name: "", type: "str" }]);

  return (
    <div className="space-y-2">
      <Label className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
        Output Fields
      </Label>

      <TextFieldRow description={textDescription} onChange={setTextDescription} />

      {extras.map((field, idx) => (
        <OutputFieldRow
          key={idx}
          field={field}
          onChange={(patch) => updateExtraAt(idx, patch)}
          onRemove={() => removeExtraAt(idx)}
        />
      ))}

      <button
        type="button"
        onClick={addExtra}
        className="inline-flex items-center gap-1 rounded-sm border border-white/[0.08] bg-transparent px-2 py-1 text-[11px] text-fg-muted hover:bg-white/[0.04] hover:text-fg-primary transition-colors"
      >
        <Plus size={11} strokeWidth={2.25} />
        Add field
      </button>

      <p className="text-[10px] text-fg-disabled">
        Extra fields are collected by the agent's final tool call. Downstream
        nodes can reference them as <span className="font-mono">{"{{ input.field_name }}"}</span>.
      </p>
    </div>
  );
}

function ArtifactRow({
  field, onChange, onRemove,
}: {
  field: ArtifactField;
  onChange: (patch: Partial<ArtifactField>) => void;
  onRemove: () => void;
}) {
  const [localName, setLocalName] = useState(field.name);
  const [localDesc, setLocalDesc] = useState(field.description ?? "");
  const nameFocused = useRef(false);
  const descFocused = useRef(false);

  useEffect(() => {
    if (!nameFocused.current) setLocalName(field.name);
  }, [field.name]);
  useEffect(() => {
    if (!descFocused.current) setLocalDesc(field.description ?? "");
  }, [field.description]);

  const commitName = () => {
    nameFocused.current = false;
    const trimmed = localName.trim();
    if (trimmed !== field.name) onChange({ name: trimmed });
    setLocalName(trimmed);
  };
  const commitDesc = () => {
    descFocused.current = false;
    const next = localDesc.trim();
    const prev = field.description ?? "";
    if (next !== prev) onChange({ description: next || undefined });
    setLocalDesc(next);
  };

  return (
    <div className="space-y-1.5 rounded-md border border-white/[0.08] bg-white/[0.02] px-2 py-2">
      <div className="flex items-center gap-1.5">
        <Input
          value={localName}
          placeholder="artifact_name"
          onChange={(e) => setLocalName(e.target.value)}
          onFocus={() => { nameFocused.current = true; }}
          onBlur={commitName}
          className="flex-1 h-7 text-[12px] font-mono"
        />
        <button
          type="button"
          onClick={onRemove}
          className="flex h-7 w-7 items-center justify-center rounded-md text-fg-disabled hover:bg-danger/10 hover:text-danger transition-colors"
          title="Remove artifact"
        >
          <Trash2 size={11} strokeWidth={1.75} />
        </button>
      </div>
      <Textarea
        value={localDesc}
        placeholder="What file/directory belongs to this artifact (guides the agent)"
        onChange={(e) => setLocalDesc(e.target.value)}
        onFocus={() => { descFocused.current = true; }}
        onBlur={commitDesc}
        rows={1}
        className="text-[12px]"
      />
    </div>
  );
}

function ArtifactsEditor({
  artifacts, onChange,
}: {
  artifacts: ArtifactField[];
  onChange: (next: ArtifactField[]) => void;
}) {
  const updateAt = (idx: number, patch: Partial<ArtifactField>) =>
    onChange(artifacts.map((a, i) => (i === idx ? { ...a, ...patch } : a)));
  const removeAt = (idx: number) =>
    onChange(artifacts.filter((_, i) => i !== idx));
  const add = () => onChange([...artifacts, { name: "" }]);

  return (
    <div className="space-y-2">
      <Label className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
        Artifacts
      </Label>

      {artifacts.map((field, idx) => (
        <ArtifactRow
          key={idx}
          field={field}
          onChange={(patch) => updateAt(idx, patch)}
          onRemove={() => removeAt(idx)}
        />
      ))}

      <button
        type="button"
        onClick={add}
        className="inline-flex items-center gap-1 rounded-sm border border-white/[0.08] bg-transparent px-2 py-1 text-[11px] text-fg-muted hover:bg-white/[0.04] hover:text-fg-primary transition-colors"
      >
        <Plus size={11} strokeWidth={2.25} />
        Add artifact
      </button>

      <p className="text-[10px] text-fg-disabled">
        Declare named file/directory outputs. The agent calls{" "}
        <span className="font-mono">save_as_artifact</span> to publish each one;
        downstream steps receive them as{" "}
        <span className="font-mono">/workspace/&#123;name&#125;</span>.
      </p>
    </div>
  );
}

export function InspectorPanel() {
  const { nodes, selectedNodeId, updateNodeData, isReadOnly } = useWorkflowBuilder();
  const readOnly = isReadOnly;

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
      {readOnly && (
        <div className="flex items-center gap-1.5 border-b border-warning/15 bg-warning/[0.04] px-4 py-2 type-caption text-warning">
          <Lock size={12} strokeWidth={2} />
          Deployed snapshot — click Edit in the toolbar to modify.
        </div>
      )}
      {/* <fieldset disabled> propagates to every native control inside;
          custom components that render plain inputs inherit the disabled
          state and can't be committed without re-enabling. */}
      <fieldset
        disabled={readOnly}
        className="flex flex-col gap-4 px-4 py-4 disabled:opacity-80"
      >
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
            <OutputFieldsEditor
              fields={(d.structured_output_fields as StructuredOutputField[]) ?? []}
              onChange={(next) => updateNodeData(node.id, "structured_output_fields", next)}
            />
            <ArtifactsEditor
              artifacts={(d.artifacts as ArtifactField[]) ?? []}
              onChange={(next) => updateNodeData(node.id, "artifacts", next)}
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
      </fieldset>
    </div>
  );
}
