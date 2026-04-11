"use client";

import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { FormSection } from "./form-section";
import { modelsApi, type ModelOption } from "@/features/agents/api/agents-api";
import { formatTokens } from "@/lib/utils/format";
import type { AgentFormData } from "./types";

interface ModelSectionProps {
  data: AgentFormData;
  setModelConfig: <K extends keyof AgentFormData["model_config"]>(
    key: K,
    value: AgentFormData["model_config"][K],
  ) => void;
}

const CAPABILITY_VARIANT: Record<string, "info" | "brand" | "success" | "warning" | "muted"> = {
  vision: "info",
  audio: "brand",
  tools: "success",
  thinking: "warning",
};

export function ModelSection({ data, setModelConfig }: ModelSectionProps) {
  const [allModels, setAllModels] = useState<ModelOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [userChangedModel, setUserChangedModel] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setModelsLoading(true);
    modelsApi
      .list()
      .then((res) => {
        if (!cancelled) setAllModels(res.models);
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Backend list is derived dynamically from whatever LiteLLM reports
  // so the form works with any provider the gateway is configured for.
  const availableBackends = Array.from(new Set(allModels.map((m) => m.backend)));
  const models = allModels.filter((m) => m.backend === data.model_config.backend);

  // Auto-pick a backend once the catalogue loads (either the current
  // value is empty or it no longer matches anything in LiteLLM).
  useEffect(() => {
    if (availableBackends.length === 0) return;
    if (availableBackends.includes(data.model_config.backend)) return;
    setModelConfig("backend", availableBackends[0]);
    setModelConfig("model", "");
  }, [availableBackends, data.model_config.backend, setModelConfig]);

  // Auto-select default model on backend change / models load
  useEffect(() => {
    if (models.length === 0) return;
    const currentValid = models.some((m) => m.id === data.model_config.model);
    if (!currentValid) {
      const defaultModel = models.find((m) => m.model_info?._ui?.default_model) ?? models[0];
      if (defaultModel) setModelConfig("model", defaultModel.id);
    }
  }, [data.model_config.backend, models, data.model_config.model, setModelConfig]);

  const selectedModelInfo = models.find((m) => m.id === data.model_config.model)?.model_info ?? {};
  const capabilities = selectedModelInfo._ui?.capabilities ?? [];
  const maxLimit =
    selectedModelInfo.max_tokens != null && selectedModelInfo.max_tokens > 0
      ? selectedModelInfo.max_tokens
      : 4000;

  // Reset max_output_tokens to a sensible default when user manually changes models
  useEffect(() => {
    if (!userChangedModel) return;
    setModelConfig("max_output_tokens", Math.min(4000, maxLimit));
  }, [data.model_config.model, maxLimit, userChangedModel, setModelConfig]);

  const currentTokens = Math.min(data.model_config.max_output_tokens, maxLimit);

  return (
    <FormSection title="Model Configuration" description="Choose the LLM backend and model">
      <Card variant="standard" className="p-5 space-y-5">
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="agent-backend">Backend</Label>
            <Select
              id="agent-backend"
              value={data.model_config.backend}
              onChange={(e) => {
                setUserChangedModel(true);
                setModelConfig("backend", e.target.value);
                setModelConfig("model", "");
              }}
              disabled={availableBackends.length === 0}
            >
              {availableBackends.map((backend) => (
                <option key={backend} value={backend}>
                  {backend}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="agent-model">Model</Label>
            <Select
              id="agent-model"
              value={data.model_config.model}
              onChange={(e) => {
                setUserChangedModel(true);
                setModelConfig("model", e.target.value);
              }}
              disabled={modelsLoading}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {capabilities.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="type-caption text-fg-disabled">Capabilities:</span>
            {capabilities.map((cap) => (
              <Badge key={cap} variant={CAPABILITY_VARIANT[cap] ?? "muted"}>
                {cap.charAt(0).toUpperCase() + cap.slice(1)}
              </Badge>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <Label>Max Output Tokens</Label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={1000}
              max={maxLimit}
              step={1000}
              value={currentTokens}
              onChange={(e) => setModelConfig("max_output_tokens", parseInt(e.target.value))}
              className="flex-1 h-2 rounded-pill appearance-none bg-raised cursor-pointer accent-info"
            />
            <span className="w-20 text-center type-code-sm text-fg-primary">
              {formatTokens(currentTokens)}
            </span>
          </div>
          <p className="type-caption text-fg-disabled">
            Maximum tokens per response (up to {formatTokens(maxLimit)})
          </p>
        </div>
      </Card>
    </FormSection>
  );
}
