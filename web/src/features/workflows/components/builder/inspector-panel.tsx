"use client";

import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { ModelSelect } from "./model-select";
import type { WorkflowNode } from "@/features/workflows/lib/types";

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
