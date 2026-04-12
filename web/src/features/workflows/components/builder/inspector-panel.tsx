"use client";

import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import type { WorkflowNode } from "@/features/workflows/lib/types";

/** Text field that edits locally and flushes to the graph on blur. */
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

  // Sync from external value when not focused (undo/redo, node switch)
  useEffect(() => {
    if (!focused) setLocal(value);
  }, [value, focused]);

  const handleBlur = () => {
    setFocused(false);
    if (local !== value) onCommit(local);
  };

  const Component = multiline ? Textarea : Input;

  return (
    <div className="mb-4 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Component
        id={id}
        value={local}
        onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setLocal(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={handleBlur}
        placeholder={placeholder}
        {...(multiline ? { rows: 4 } : {})}
      />
      {hint && <p className="type-caption text-fg-disabled">{hint}</p>}
    </div>
  );
}

export function InspectorPanel() {
  const { nodes, selectedNodeId, updateNodeData } = useWorkflowBuilder();

  // Read from provider's nodes array (reactive to undo/redo) instead of getNode()
  const node = selectedNodeId
    ? (nodes.find((n) => n.id === selectedNodeId) as WorkflowNode | undefined)
    : null;

  if (!node) {
    return (
      <div className="w-64 shrink-0 overflow-y-auto border-l border-white/[0.06] bg-canvas p-4">
        <p className="type-caption text-fg-muted">Select a node to edit its properties.</p>
      </div>
    );
  }

  const d = node.data as Record<string, unknown>;
  const commit = (key: string) => (value: string) => updateNodeData(node.id, key, value);

  return (
    <div className="w-64 shrink-0 overflow-y-auto border-l border-white/[0.06] bg-canvas p-4">
      <h2 className="mb-4 type-caption-bold text-fg-muted uppercase tracking-wider">Inspector</h2>

      <NodeField
        id="node-label"
        label="Label"
        value={(d.label as string) ?? ""}
        onCommit={commit("label")}
      />

      {node.type === "agent_step" && (
        <>
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

      <div className="mt-4 pt-4 border-t border-white/[0.06]">
        <p className="type-caption text-fg-disabled">
          Type: <span className="text-fg-muted">{node.type}</span>
        </p>
        <p className="type-caption text-fg-disabled">
          ID: <span className="text-fg-muted font-mono text-[10px]">{node.id}</span>
        </p>
      </div>
    </div>
  );
}
