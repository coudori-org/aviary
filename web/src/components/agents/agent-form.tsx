"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type { ModelInfo } from "@/types";

interface AgentFormData {
  name: string;
  slug: string;
  description: string;
  instruction: string;
  model_config: {
    backend: string;
    model: string;
    temperature: number | null;
    top_p: number | null;
    top_k: number | null;
    num_ctx: number | null;
    max_output_tokens: number;
  };
  tools: string[];
  visibility: string;
  category: string;
}

interface AgentFormProps {
  initialData?: Partial<AgentFormData>;
  onSubmit: (data: AgentFormData) => Promise<void>;
  submitLabel: string;
}

const defaultData: AgentFormData = {
  name: "",
  slug: "",
  description: "",
  instruction: "",
  model_config: {
    backend: "claude",
    model: "",
    temperature: null,
    top_p: null,
    top_k: null,
    num_ctx: null,
    max_output_tokens: 4000,
  },
  tools: [],
  visibility: "private",
  category: "",
};

interface ModelOption {
  id: string;
  name: string;
  is_default?: boolean;
}

// Capability badge styles — known caps get distinct colors, others get a muted style
const CAP_STYLES: Record<string, string> = {
  vision: "bg-blue-500/10 text-blue-400 ring-blue-500/20",
  audio: "bg-purple-500/10 text-purple-400 ring-purple-500/20",
  tools: "bg-green-500/10 text-green-400 ring-green-500/20",
  thinking: "bg-amber-500/10 text-amber-400 ring-amber-500/20",
  _default: "bg-zinc-500/10 text-zinc-400 ring-zinc-500/20",
};

// Discrete context window steps
const CTX_STEPS = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576];
const CTX_LABELS = ["4K", "8K", "16K", "32K", "64K", "128K", "256K", "512K", "1M"];

function ctxValueToIndex(value: number | null, maxCtx: number | null): number {
  if (value == null) return 3; // default to 32K
  const available = CTX_STEPS.filter((s) => !maxCtx || s <= maxCtx);
  let closest = 0;
  for (let i = 0; i < available.length; i++) {
    if (Math.abs(available[i] - value) < Math.abs(available[closest] - value)) closest = i;
  }
  return closest;
}

function formatCtxLabel(value: number | null): string {
  if (value == null) return "Default";
  const idx = CTX_STEPS.indexOf(value);
  if (idx >= 0) return CTX_LABELS[idx];
  if (value >= 1048576) return `${(value / 1048576).toFixed(1)}M`;
  return `${Math.round(value / 1024)}K`;
}

export function AgentForm({ initialData, onSubmit, submitLabel }: AgentFormProps) {
  const [data, setData] = useState<AgentFormData>(() => {
    const merged = { ...defaultData, ...initialData };
    merged.model_config = { ...defaultData.model_config, ...initialData?.model_config };
    return merged;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const fetchSeq = useRef(0);

  const fetchModels = useCallback(async (backend: string, currentModel?: string) => {
    setModelsLoading(true);
    try {
      const res = await apiFetch<{ models: ModelOption[]; error?: string }>(`/inference/${backend}/models`);
      setModels(res.models);
      // Auto-select: keep current model if it exists in the list, otherwise pick the default-flagged model or first
      if (!currentModel || !res.models.some((m) => m.id === currentModel)) {
        const defaultModel = res.models.find((m) => m.is_default) ?? res.models[0];
        if (defaultModel) {
          setData((prev) => ({
            ...prev,
            model_config: { ...prev.model_config, model: defaultModel.id },
          }));
        }
      }
    } catch {
      setModels([]);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels(data.model_config.backend, data.model_config.model);
  }, [data.model_config.backend, fetchModels]);

  // Fetch model info when model changes, auto-populate defaults
  useEffect(() => {
    const { backend, model } = data.model_config;
    if (!model) {
      setModelInfo(null);
      return;
    }
    const seq = ++fetchSeq.current;
    (async () => {
      try {
        const info = await apiFetch<ModelInfo>(
          `/inference/${backend}/model-info?model=${encodeURIComponent(model)}`
        );
        if (seq !== fetchSeq.current) return; // stale
        setModelInfo(info);
        // Auto-populate defaults (only for fields the user hasn't manually set yet on this model)
        setData((prev) => ({
          ...prev,
          model_config: {
            ...prev.model_config,
            temperature: info.defaults.temperature ?? prev.model_config.temperature,
            top_p: info.defaults.top_p ?? prev.model_config.top_p,
            top_k: info.defaults.top_k != null ? info.defaults.top_k : prev.model_config.top_k,
            num_ctx: info.defaults.num_ctx ?? info.limits.max_context_length ?? prev.model_config.num_ctx,
          },
        }));
      } catch {
        if (seq === fetchSeq.current) setModelInfo(null);
      }
    })();
  }, [data.model_config.backend, data.model_config.model]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await onSubmit(data);
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const updateField = <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) => {
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const updateModelConfig = (key: string, value: string | number | null) => {
    setData((prev) => ({
      ...prev,
      model_config: { ...prev.model_config, [key]: value },
    }));
  };

  const handleNameChange = (name: string) => {
    updateField("name", name);
    if (!initialData?.slug) {
      const slug = name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      updateField("slug", slug);
    }
  };

  const maxCtx = modelInfo?.limits.max_context_length ?? null;
  const availableCtxSteps = CTX_STEPS.filter((s) => !maxCtx || s <= maxCtx);
  const availableCtxLabels = CTX_LABELS.slice(0, availableCtxSteps.length);
  const backend = data.model_config.backend;
  const showSamplingControls = !!data.model_config.model && (backend === "ollama" || backend === "vllm");

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {error && (
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Basic info */}
      <section className="space-y-5">
        <div className="mb-1">
          <h2 className="text-sm font-semibold text-foreground">Basic Information</h2>
          <p className="text-xs text-muted-foreground">Name and identity for your agent</p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={data.name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="e.g. Code Reviewer"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="slug">Slug</Label>
            <Input
              id="slug"
              value={data.slug}
              onChange={(e) => updateField("slug", e.target.value)}
              placeholder="code-reviewer"
              pattern="[a-z0-9][a-z0-9\-]*[a-z0-9]"
              required
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Input
            id="description"
            value={data.description}
            onChange={(e) => updateField("description", e.target.value)}
            placeholder="A brief description of what this agent does"
          />
        </div>
      </section>

      {/* System instruction */}
      <section className="space-y-5">
        <div className="mb-1">
          <h2 className="text-sm font-semibold text-foreground">Behavior</h2>
          <p className="text-xs text-muted-foreground">Define how the agent should behave and respond</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="instruction">System Instruction</Label>
          <Textarea
            id="instruction"
            value={data.instruction}
            onChange={(e) => updateField("instruction", e.target.value)}
            placeholder="You are a helpful assistant that specializes in..."
            rows={8}
            className="font-mono text-xs leading-relaxed"
            required
          />
        </div>
      </section>

      {/* Model config */}
      <section className="space-y-5">
        <div className="mb-1">
          <h2 className="text-sm font-semibold text-foreground">Model Configuration</h2>
          <p className="text-xs text-muted-foreground">Choose the LLM backend and tuning parameters</p>
        </div>

        <div className="rounded-xl border border-border/60 bg-card p-5 space-y-5">
          {/* Backend + Model row */}
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="backend">Backend</Label>
              <Select
                id="backend"
                value={data.model_config.backend}
                onChange={(e) => {
                  updateModelConfig("backend", e.target.value);
                  updateModelConfig("model", "");
                  setModelInfo(null);
                }}
              >
                <option value="claude">Claude API</option>
                <option value="vllm">vLLM (Local)</option>
                <option value="ollama">Ollama (Local)</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              <Select
                id="model"
                value={data.model_config.model}
                onChange={(e) => updateModelConfig("model", e.target.value)}
                disabled={modelsLoading}
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </Select>
            </div>
          </div>

          {/* Capabilities badges */}
          {modelInfo && modelInfo.capabilities.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] text-muted-foreground/60">Capabilities:</span>
              {modelInfo.capabilities.map((cap) => {
                const style = CAP_STYLES[cap] ?? CAP_STYLES._default;
                return (
                  <span key={cap} className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${style}`}>
                    {cap.charAt(0).toUpperCase() + cap.slice(1)}
                  </span>
                );
              })}
            </div>
          )}

          {/* Max Output Tokens (all backends) */}
          <div className="space-y-2">
            <Label>Max Output Tokens</Label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={1000}
                max={32000}
                step={1000}
                value={data.model_config.max_output_tokens ?? 4000}
                onChange={(e) => updateModelConfig("max_output_tokens", parseInt(e.target.value))}
                className="flex-1 h-2 rounded-full appearance-none bg-secondary cursor-pointer accent-primary"
              />
              <span className="w-20 text-center text-sm font-mono text-foreground">
                {((data.model_config.max_output_tokens ?? 4000) / 1000).toFixed(0)}K
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground/60">
              Max tokens per response. Lower values save context for local models.
            </p>
          </div>

          {/* Advanced Options (Ollama & vLLM) */}
          {showSamplingControls && (
            <div className="space-y-5 border-t border-border/40 pt-5">
              <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider">Advanced Options</p>

              {/* Context Window — Ollama (editable) */}
              {backend === "ollama" && (
                <div className="space-y-2">
                  <Label>Context Window</Label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={0}
                      max={availableCtxSteps.length - 1}
                      step={1}
                      value={ctxValueToIndex(data.model_config.num_ctx, maxCtx)}
                      onChange={(e) => {
                        const idx = parseInt(e.target.value);
                        updateModelConfig("num_ctx", availableCtxSteps[idx]);
                      }}
                      className="flex-1 h-2 rounded-full appearance-none bg-secondary cursor-pointer accent-primary"
                    />
                    <span className="w-16 text-center text-sm font-mono text-foreground">
                      {formatCtxLabel(data.model_config.num_ctx)}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 flex justify-between text-[10px] text-muted-foreground/40 px-0.5">
                      {availableCtxLabels.map((label) => (
                        <span key={label}>{label}</span>
                      ))}
                    </div>
                    <span className="w-16" />
                  </div>
                </div>
              )}

              {/* Context Window — vLLM (read-only) */}
              {backend === "vllm" && (modelInfo?.limits.active_context_length || maxCtx) && (() => {
                const activeCtx = modelInfo?.limits.active_context_length ?? maxCtx;
                const ctxStepsForVllm = CTX_STEPS.filter((s) => !maxCtx || s <= maxCtx);
                const ctxLabelsForVllm = CTX_LABELS.slice(0, ctxStepsForVllm.length);
                return (
                  <div className="space-y-2">
                    <Label>Context Window <span className="text-[11px] font-normal text-muted-foreground/60">(configured on backend)</span></Label>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min={0}
                        max={ctxStepsForVllm.length - 1}
                        step={1}
                        value={ctxValueToIndex(activeCtx, maxCtx)}
                        disabled
                        className="flex-1 h-2 rounded-full appearance-none bg-secondary cursor-not-allowed accent-primary opacity-50"
                      />
                      <span className="w-16 text-center text-sm font-mono text-foreground">
                        {formatCtxLabel(activeCtx)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex-1 flex justify-between text-[10px] text-muted-foreground/40 px-0.5">
                        {ctxLabelsForVllm.map((label) => (
                          <span key={label}>{label}</span>
                        ))}
                      </div>
                      <span className="w-16" />
                    </div>
                  </div>
                );
              })()}

              {/* Temperature */}
              <div className="space-y-2">
                <Label htmlFor="temperature">Temperature</Label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={2}
                    step={0.05}
                    value={data.model_config.temperature ?? 1.0}
                    onChange={(e) => updateModelConfig("temperature", parseFloat(e.target.value))}
                    className="flex-1 h-2 rounded-full appearance-none bg-secondary cursor-pointer accent-primary"
                  />
                  <Input
                    id="temperature"
                    type="number"
                    min={0}
                    max={2}
                    step={0.05}
                    value={data.model_config.temperature ?? ""}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v)) updateModelConfig("temperature", v);
                    }}
                    className="w-20 text-center"
                  />
                </div>
                <p className="text-[11px] text-muted-foreground/60">0 = deterministic, 1+ = more creative</p>
              </div>

              <div className="grid gap-5 sm:grid-cols-2">
                {/* top_p */}
                <div className="space-y-2">
                  <Label htmlFor="top_p">Top P</Label>
                  <div className="flex items-center gap-3">
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={data.model_config.top_p ?? 0.95}
                      onChange={(e) => updateModelConfig("top_p", parseFloat(e.target.value))}
                      className="flex-1 h-2 rounded-full appearance-none bg-secondary cursor-pointer accent-primary"
                    />
                    <Input
                      id="top_p"
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={data.model_config.top_p ?? ""}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        updateModelConfig("top_p", isNaN(v) ? null : v);
                      }}
                      placeholder="auto"
                      className="w-20 text-center"
                    />
                  </div>
                  <p className="text-[11px] text-muted-foreground/60">Nucleus sampling threshold</p>
                </div>

                {/* top_k */}
                <div className="space-y-2">
                  <Label htmlFor="top_k">Top K</Label>
                  <Input
                    id="top_k"
                    type="number"
                    min={0}
                    max={500}
                    value={data.model_config.top_k ?? ""}
                    onChange={(e) => {
                      const v = parseInt(e.target.value);
                      updateModelConfig("top_k", isNaN(v) ? null : v);
                    }}
                    placeholder="auto"
                  />
                  <p className="text-[11px] text-muted-foreground/60">Top-K sampling (0 = disabled)</p>
                </div>
              </div>
            </div>
          )}

        </div>
      </section>

      {/* Access & category */}
      <section className="space-y-5">
        <div className="mb-1">
          <h2 className="text-sm font-semibold text-foreground">Access & Organization</h2>
          <p className="text-xs text-muted-foreground">Control who can discover and use this agent</p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="visibility">Visibility</Label>
            <Select
              id="visibility"
              value={data.visibility}
              onChange={(e) => updateField("visibility", e.target.value)}
            >
              <option value="private">Private — Only you</option>
              <option value="team">Team — Your team members</option>
              <option value="public">Public — Everyone</option>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="category">Category</Label>
            <Input
              id="category"
              value={data.category}
              onChange={(e) => updateField("category", e.target.value)}
              placeholder="e.g. coding, writing, research"
            />
          </div>
        </div>
      </section>

      {/* Submit */}
      <div className="flex items-center justify-end gap-3 border-t border-border/40 pt-6">
        <Button type="submit" disabled={loading} size="lg">
          {loading ? (
            <span className="flex items-center gap-2">
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Saving...
            </span>
          ) : (
            submitLabel
          )}
        </Button>
      </div>
    </form>
  );
}
