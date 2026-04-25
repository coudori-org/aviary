"use client";

import { useState, useEffect, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { modelsApi, type ModelOption } from "@/features/agents/api/agents-api";

function SettingsField({
  id,
  label,
  value,
  onCommit,
  multiline,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onCommit: (value: string) => void;
  multiline?: boolean;
  placeholder?: string;
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
      <Label htmlFor={id} className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">
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
        {...(multiline ? { rows: 3 } : {})}
      />
    </div>
  );
}

export function SettingsPanel() {
  const { workflowId, workflowName } = useWorkflowBuilder();
  const [workflow, setWorkflow] = useState<{
    name: string; slug: string; description: string;
    model_config: { backend: string; model: string };
  } | null>(null);
  const [allModels, setAllModels] = useState<ModelOption[]>([]);

  useEffect(() => {
    workflowsApi.get(workflowId).then((w) => {
      setWorkflow({
        name: w.name,
        slug: w.slug,
        description: w.description ?? "",
        model_config: w.model_config ?? { backend: "", model: "" },
      });
    });
    modelsApi.list().then((res) => setAllModels(res.models));
  }, [workflowId]);

  const save = useCallback(
    (patch: Record<string, unknown>) => {
      workflowsApi.update(workflowId, patch);
    },
    [workflowId],
  );

  if (!workflow) return null;

  const backends = Array.from(new Set(allModels.map((m) => m.backend)));
  const models = allModels.filter((m) => m.backend === workflow.model_config.backend);

  return (
    <div className="flex flex-col gap-4 px-3 py-4">
      <SettingsField
        id="wf-name"
        label="Name"
        value={workflow.name}
        onCommit={(v) => { setWorkflow({ ...workflow, name: v }); save({ name: v }); }}
        placeholder="Workflow name"
      />
      <SettingsField
        id="wf-description"
        label="Description"
        value={workflow.description}
        onCommit={(v) => { setWorkflow({ ...workflow, description: v }); save({ description: v }); }}
        multiline
        placeholder="What does this workflow do?"
      />

      <div className="space-y-1.5">
        <Label htmlFor="wf-backend" className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">
          Backend
        </Label>
        <Select
          id="wf-backend"
          value={workflow.model_config.backend}
          onChange={(e) => {
            const b = e.target.value;
            const filtered = allModels.filter((m) => m.backend === b);
            const def = filtered.find((m) => m.model_info?._ui?.default_model) ?? filtered[0];
            const mc = { backend: b, model: def?.id ?? "" };
            setWorkflow({ ...workflow, model_config: mc });
            save({ model_config: mc });
          }}
          className="text-[13px]"
        >
          {backends.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </Select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="wf-model" className="text-[11px] font-medium text-fg-muted uppercase tracking-wider">
          Model
        </Label>
        <Select
          id="wf-model"
          value={workflow.model_config.model}
          onChange={(e) => {
            const mc = { ...workflow.model_config, model: e.target.value };
            setWorkflow({ ...workflow, model_config: mc });
            save({ model_config: mc });
          }}
          className="text-[13px]"
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </Select>
      </div>
    </div>
  );
}
