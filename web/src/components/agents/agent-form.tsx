"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { ToolSelector } from "./tool-selector";
import type { McpToolInfo } from "@/types";

interface AgentFormData {
  name: string;
  slug: string;
  description: string;
  instruction: string;
  model_config: {
    backend: string;
    model: string;
    max_output_tokens: number;
  };
  tools: string[];
  mcp_tool_ids: string[];
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
    max_output_tokens: 4000,
  },
  tools: [],
  mcp_tool_ids: [],
  visibility: "private",
  category: "",
};

interface ModelOption {
  id: string;
  name: string;
  backend: string;
  model_info: Record<string, any>;
}

// Capability badge styles — known caps get distinct colors, others get a muted style
const CAP_STYLES: Record<string, string> = {
  vision: "bg-blue-500/10 text-blue-400 ring-blue-500/20",
  audio: "bg-purple-500/10 text-purple-400 ring-purple-500/20",
  tools: "bg-green-500/10 text-green-400 ring-green-500/20",
  thinking: "bg-amber-500/10 text-amber-400 ring-amber-500/20",
  _default: "bg-zinc-500/10 text-zinc-400 ring-zinc-500/20",
};

export function AgentForm({ initialData, onSubmit, submitLabel }: AgentFormProps) {
  const [data, setData] = useState<AgentFormData>(() => {
    const merged = { ...defaultData, ...initialData };
    merged.model_config = { ...defaultData.model_config, ...initialData?.model_config };
    return merged;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allModels, setAllModels] = useState<ModelOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [toolSelectorOpen, setToolSelectorOpen] = useState(false);
  const [boundToolNames, setBoundToolNames] = useState<Map<string, string>>(new Map());

  // Fetch all models once on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setModelsLoading(true);
      try {
        const res = await apiFetch<{ models: ModelOption[] }>("/inference/models");
        if (!cancelled) setAllModels(res.models);
      } catch {
        if (!cancelled) setAllModels([]);
      } finally {
        if (!cancelled) setModelsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Filter models by selected backend
  const models = allModels.filter((m) => m.backend === data.model_config.backend);

  // Auto-select model when backend changes or models load
  useEffect(() => {
    if (models.length === 0) return;
    const currentValid = models.some((m) => m.id === data.model_config.model);
    if (!currentValid) {
      const defaultModel = models.find((m) => m.model_info?._ui?.default_model) ?? models[0];
      if (defaultModel) {
        setData((prev) => ({
          ...prev,
          model_config: { ...prev.model_config, model: defaultModel.id },
        }));
      }
    }
  }, [data.model_config.backend, models.length]);

  // Derive selected model info from models list
  const selectedModelInfo = models.find((m) => m.id === data.model_config.model)?.model_info ?? {};

  // Track whether the user has manually changed the model (skip reset on initial load)
  const [userChangedModel, setUserChangedModel] = useState(false);

  // Auto-set max_output_tokens default only when user explicitly changes model
  useEffect(() => {
    if (!userChangedModel) return;
    const maxTokens = selectedModelInfo.max_tokens as number | undefined;
    const maxLimit = maxTokens != null && maxTokens > 0 ? maxTokens : 4000;
    const defaultVal = Math.min(4000, maxLimit);
    setData((prev) => ({
      ...prev,
      model_config: { ...prev.model_config, max_output_tokens: defaultVal },
    }));
  }, [data.model_config.model, selectedModelInfo.max_tokens, userChangedModel]);

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

  const updateModelConfig = (key: string, value: string | number) => {
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
          <p className="text-xs text-muted-foreground">Choose the LLM backend and model</p>
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
                  setUserChangedModel(true);
                  updateModelConfig("backend", e.target.value);
                  updateModelConfig("model", "");
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
                onChange={(e) => { setUserChangedModel(true); updateModelConfig("model", e.target.value); }}
                disabled={modelsLoading}
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </Select>
            </div>
          </div>

          {/* Capabilities badges */}
          {(selectedModelInfo._ui?.capabilities as string[] ?? []).length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] text-muted-foreground/60">Capabilities:</span>
              {(selectedModelInfo._ui.capabilities as string[]).map((cap) => {
                const style = CAP_STYLES[cap] ?? CAP_STYLES._default;
                return (
                  <span key={cap} className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${style}`}>
                    {cap.charAt(0).toUpperCase() + cap.slice(1)}
                  </span>
                );
              })}
            </div>
          )}

          {/* Max Output Tokens */}
          {(() => {
            const maxTokens = selectedModelInfo.max_tokens as number | undefined;
            const maxVal = maxTokens != null && maxTokens > 0 ? maxTokens : 4000;
            const current = Math.min(data.model_config.max_output_tokens, maxVal);
            return (
              <div className="space-y-2">
                <Label>Max Output Tokens</Label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={1000}
                    max={maxVal}
                    step={1000}
                    value={current}
                    onChange={(e) => updateModelConfig("max_output_tokens", parseInt(e.target.value))}
                    className="flex-1 h-2 rounded-full appearance-none bg-secondary cursor-pointer accent-primary"
                  />
                  <span className="w-20 text-center text-sm font-mono text-foreground">
                    {`${(current / 1000).toFixed(0)}k`}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground/60">
                  Maximum tokens per response (up to {`${(maxVal / 1000).toFixed(0)}k`})
                </p>
              </div>
            );
          })()}

        </div>
      </section>

      {/* Tools & Integrations */}
      <section className="space-y-5">
        <div className="mb-1">
          <h2 className="text-sm font-semibold text-foreground">Tools & Integrations</h2>
          <p className="text-xs text-muted-foreground">Connect external tools via MCP servers</p>
        </div>

        <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4">
          {data.mcp_tool_ids.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {data.mcp_tool_ids.map((id) => (
                <span
                  key={id}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20"
                >
                  {boundToolNames.get(id) || id.slice(0, 8)}
                  <button
                    type="button"
                    onClick={() => {
                      const next = data.mcp_tool_ids.filter((t) => t !== id);
                      updateField("mcp_tool_ids", next);
                    }}
                    className="ml-0.5 text-primary/60 hover:text-primary"
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No tools connected yet.</p>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setToolSelectorOpen(true)}
          >
            Browse Tools
          </Button>
        </div>

        <ToolSelector
          selectedToolIds={data.mcp_tool_ids}
          onChange={(ids) => updateField("mcp_tool_ids", ids)}
          open={toolSelectorOpen}
          onClose={() => setToolSelectorOpen(false)}
        />
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
