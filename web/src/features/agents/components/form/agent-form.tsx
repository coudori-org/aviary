"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { extractErrorMessage } from "@/lib/http";
import { useAgentForm } from "./use-agent-form";
import { BasicInfoSection } from "./basic-info-section";
import { InstructionSection } from "./instruction-section";
import { ModelSection } from "./model-section";
import { ToolsSection } from "./tools-section";
import { AccessSection } from "./access-section";
import type { AgentFormData } from "./types";
import type { McpToolInfo } from "@/types";

interface AgentFormProps {
  initialData?: Partial<AgentFormData>;
  initialToolInfo?: Map<string, McpToolInfo>;
  onSubmit: (data: AgentFormData) => Promise<void>;
  submitLabel: string;
}

/**
 * AgentForm — top-level orchestrator. All real logic lives in section
 * components and the useAgentForm hook. This file is intentionally tiny
 * (~50 lines): it composes, it doesn't decide.
 */
export function AgentForm({ initialData, initialToolInfo, onSubmit, submitLabel }: AgentFormProps) {
  const { data, setField, setModelConfig, setName } = useAgentForm(initialData);
  const [toolInfoMap, setToolInfoMap] = useState<Map<string, McpToolInfo>>(
    initialToolInfo ?? new Map(),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-10">
      {error && (
        <div className="rounded-md border border-danger/30 bg-danger/[0.04] p-4 type-caption text-danger">
          {error}
        </div>
      )}

      <BasicInfoSection data={data} onNameChange={setName} setField={setField} />
      <InstructionSection data={data} setField={setField} />
      <ModelSection data={data} setModelConfig={setModelConfig} />
      <ToolsSection
        data={data}
        setField={setField}
        toolInfoMap={toolInfoMap}
        setToolInfoMap={setToolInfoMap}
      />
      <AccessSection data={data} setField={setField} />

      <div className="flex items-center justify-end border-t border-white/[0.06] pt-6">
        <Button type="submit" disabled={submitting} variant="cta" size="lg">
          {submitting ? (
            <>
              <Spinner size={14} className="text-fg-on-light" />
              Saving…
            </>
          ) : (
            submitLabel
          )}
        </Button>
      </div>
    </form>
  );
}
