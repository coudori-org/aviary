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
    temperature: number;
    top_p: number | null;
    top_k: number | null;
    num_ctx: number | null;
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
    model: "default",
    temperature: 0.7,
    top_p: null,
    top_k: null,
    num_ctx: null,
  },
  tools: [],
  visibility: "private",
  category: "",
};

interface ModelOption {
  id: string;
  name: string;
}

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

  const fetchModels = useCallback(async (backend: string) => {
    setModelsLoading(true);
    try {
      const res = await apiFetch<{ models: ModelOption[]; error?: string }>(`/inference/${backend}/models`);
      setModels(res.models);
    } catch {
      setModels([]);
    } finally {
      setModelsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels(data.model_config.backend);
  }, [data.model_config.backend, fetchModels]);

  // Fetch model info when model changes, auto-populate defaults
  useEffect(() => {
    const { backend, model } = data.model_config;
    if (model === "default") {
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
            num_ctx: info.defaults.num_ctx ?? prev.model_config.num_ctx,
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
  const isNonClaude = data.model_config.backend !== "claude";

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
                  updateModelConfig("model", "default");
                  setModelInfo(null);
                }}
              >
                <option value="claude">Claude API</option>
                <option value="ollama">Ollama (Local)</option>
                <option value="vllm">vLLM (Local)</option>
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
                <option value="default">Default</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </Select>
            </div>
          </div>

          {/* Capabilities badges */}
          {modelInfo && (
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-muted-foreground/60">Capabilities:</span>
              {modelInfo.capabilities.vision && (
                <span className="inline-flex items-center rounded-md bg-blue-500/10 px-2 py-0.5 text-[11px] font-medium text-blue-400 ring-1 ring-inset ring-blue-500/20">Vision</span>
              )}
              {modelInfo.capabilities.audio && (
                <span className="inline-flex items-center rounded-md bg-purple-500/10 px-2 py-0.5 text-[11px] font-medium text-purple-400 ring-1 ring-inset ring-purple-500/20">Audio</span>
              )}
              {modelInfo.capabilities.tools && (
                <span className="inline-flex items-center rounded-md bg-green-500/10 px-2 py-0.5 text-[11px] font-medium text-green-400 ring-1 ring-inset ring-green-500/20">Tools</span>
              )}
              {!modelInfo.capabilities.vision && !modelInfo.capabilities.audio && !modelInfo.capabilities.tools && (
                <span className="text-[11px] text-muted-foreground/40">Text only</span>
              )}
              {maxCtx && (
                <span className="ml-auto text-[11px] text-muted-foreground/50">
                  Max context: {formatCtxLabel(maxCtx)}
                </span>
              )}
            </div>
          )}

          {/* Context Window (non-Claude) */}
          {isNonClaude && (
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
              <div className="flex justify-between text-[10px] text-muted-foreground/40 px-0.5">
                {availableCtxLabels.map((label) => (
                  <span key={label}>{label}</span>
                ))}
              </div>
            </div>
          )}

          {/* Advanced Sampling (non-Claude only) */}
          {isNonClaude && (
            <div className="space-y-5 border-t border-border/40 pt-5">
              <p className="text-[11px] font-medium text-muted-foreground/70 uppercase tracking-wider">Advanced Sampling</p>

              {/* Temperature */}
              <div className="space-y-2">
                <Label htmlFor="temperature">Temperature</Label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={2}
                    step={0.05}
                    value={data.model_config.temperature}
                    onChange={(e) => updateModelConfig("temperature", parseFloat(e.target.value))}
                    className="flex-1 h-2 rounded-full appearance-none bg-secondary cursor-pointer accent-primary"
                  />
                  <Input
                    id="temperature"
                    type="number"
                    min={0}
                    max={2}
                    step={0.05}
                    value={data.model_config.temperature}
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
