"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { EgressRule } from "@/types";

interface AgentFormData {
  name: string;
  slug: string;
  description: string;
  instruction: string;
  model_config: {
    backend: string;
    model: string;
    temperature: number;
    maxTokens: number;
  };
  tools: string[];
  visibility: string;
  category: string;
  policy: {
    allowedEgress: EgressRule[];
  };
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
    model: "claude-sonnet-4-20250514",
    temperature: 0.7,
    maxTokens: 8192,
  },
  tools: [],
  visibility: "private",
  category: "",
  policy: {
    allowedEgress: [],
  },
};

const claudeModels = [
  "claude-sonnet-4-20250514",
  "claude-opus-4-20250514",
];

export function AgentForm({ initialData, onSubmit, submitLabel }: AgentFormProps) {
  const [data, setData] = useState<AgentFormData>({ ...defaultData, ...initialData });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const addEgressRule = () => {
    setData((prev) => ({
      ...prev,
      policy: {
        ...prev.policy,
        allowedEgress: [
          ...prev.policy.allowedEgress,
          { name: "", domain: "", ports: [] },
        ],
      },
    }));
  };

  const removeEgressRule = (index: number) => {
    setData((prev) => ({
      ...prev,
      policy: {
        ...prev.policy,
        allowedEgress: prev.policy.allowedEgress.filter((_, i) => i !== index),
      },
    }));
  };

  const updateEgressRule = (index: number, field: string, value: any) => {
    setData((prev) => ({
      ...prev,
      policy: {
        ...prev.policy,
        allowedEgress: prev.policy.allowedEgress.map((rule, i) =>
          i === index ? { ...rule, [field]: value } : rule
        ),
      },
    }));
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
          <p className="text-xs text-muted-foreground">Choose the LLM backend and tuning parameters</p>
        </div>

        <div className="rounded-xl border border-border/60 bg-card p-5 space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="backend">Backend</Label>
              <Select
                id="backend"
                value={data.model_config.backend}
                onChange={(e) => updateModelConfig("backend", e.target.value)}
              >
                <option value="claude">Claude API</option>
                <option value="ollama">Ollama (Local)</option>
                <option value="vllm">vLLM (Local)</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              {data.model_config.backend === "claude" ? (
                <Select
                  id="model"
                  value={data.model_config.model}
                  onChange={(e) => updateModelConfig("model", e.target.value)}
                >
                  {claudeModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </Select>
              ) : (
                <Input
                  id="model"
                  value={data.model_config.model}
                  onChange={(e) => updateModelConfig("model", e.target.value)}
                  placeholder={data.model_config.backend === "ollama" ? "llama3.3:70b" : "meta-llama/Llama-3.3-70B-Instruct"}
                />
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="temperature">Temperature</Label>
              <Input
                id="temperature"
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={data.model_config.temperature}
                onChange={(e) => updateModelConfig("temperature", parseFloat(e.target.value))}
              />
              <p className="text-[11px] text-muted-foreground/60">0 = deterministic, 1+ = more creative</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="maxTokens">Max Tokens</Label>
              <Input
                id="maxTokens"
                type="number"
                min={1}
                max={200000}
                value={data.model_config.maxTokens}
                onChange={(e) => updateModelConfig("maxTokens", parseInt(e.target.value))}
              />
              <p className="text-[11px] text-muted-foreground/60">Maximum response length per turn</p>
            </div>
          </div>
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

      {/* Network Policy */}
      <section className="space-y-5">
        <div className="mb-1">
          <h2 className="text-sm font-semibold text-foreground">Network Policy</h2>
          <p className="text-xs text-muted-foreground">
            Control which external endpoints this agent can access. All outbound traffic is blocked by default.
          </p>
        </div>

        <div className="rounded-xl border border-border/60 bg-card p-5 space-y-4">
          {data.policy.allowedEgress.length === 0 && (
            <p className="text-xs text-muted-foreground/60 py-2 text-center">
              No egress rules configured. All external HTTP/HTTPS traffic is blocked.
            </p>
          )}

          {data.policy.allowedEgress.map((rule, index) => (
            <div key={index} className="flex items-start gap-3 rounded-lg border border-border/40 bg-muted/30 p-3">
              <div className="flex-1 grid gap-3 sm:grid-cols-[1fr_auto_1fr_auto]">
                <div className="space-y-1">
                  <Label className="text-[11px]">Name</Label>
                  <Input
                    value={rule.name}
                    onChange={(e) => updateEgressRule(index, "name", e.target.value)}
                    placeholder="e.g. GitHub API"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[11px]">Type</Label>
                  <Select
                    value={rule.domain !== undefined ? "domain" : "cidr"}
                    onChange={(e) => {
                      if (e.target.value === "domain") {
                        updateEgressRule(index, "domain", rule.cidr || "");
                        updateEgressRule(index, "cidr", undefined);
                      } else {
                        updateEgressRule(index, "cidr", rule.domain || "");
                        updateEgressRule(index, "domain", undefined);
                      }
                    }}
                    className="h-8 text-xs"
                  >
                    <option value="domain">Domain</option>
                    <option value="cidr">CIDR</option>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-[11px]">
                    {rule.domain !== undefined ? "Domain" : "CIDR"}
                  </Label>
                  <Input
                    value={rule.domain !== undefined ? (rule.domain || "") : (rule.cidr || "")}
                    onChange={(e) => {
                      if (rule.domain !== undefined) {
                        updateEgressRule(index, "domain", e.target.value);
                      } else {
                        updateEgressRule(index, "cidr", e.target.value);
                      }
                    }}
                    placeholder={rule.domain !== undefined ? "*.example.com" : "10.0.0.0/8"}
                    className="h-8 text-xs font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-[11px]">Ports</Label>
                  <Input
                    value={rule.ports.map((p) => p.port).join(", ")}
                    onChange={(e) => {
                      const ports = e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter((s) => s && !isNaN(Number(s)))
                        .map((s) => ({ port: Number(s), protocol: "TCP" as const }));
                      updateEgressRule(index, "ports", ports);
                    }}
                    placeholder="All"
                    className="h-8 text-xs font-mono"
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={() => removeEgressRule(index)}
                className="mt-5 p-1.5 text-muted-foreground/60 hover:text-destructive transition-colors rounded-md hover:bg-destructive/10"
                title="Remove rule"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}

          <button
            type="button"
            onClick={addEgressRule}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add egress rule
          </button>
        </div>

        <p className="text-[11px] text-muted-foreground/60">
          Domain patterns: <code className="bg-muted px-1 rounded">api.github.com</code> (exact), <code className="bg-muted px-1 rounded">*.github.com</code> (wildcard), <code className="bg-muted px-1 rounded">*</code> (all).
          Ports: comma-separated (e.g. <code className="bg-muted px-1 rounded">443, 8080</code>), leave empty to allow all.
        </p>
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
