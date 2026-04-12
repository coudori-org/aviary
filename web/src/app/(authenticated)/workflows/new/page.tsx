"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { modelsApi, type ModelOption } from "@/features/agents/api/agents-api";
import { routes } from "@/lib/constants/routes";
import { slugify } from "@/lib/utils/format";

export default function NewWorkflowPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [backend, setBackend] = useState("");
  const [model, setModel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const [allModels, setAllModels] = useState<ModelOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    modelsApi
      .list()
      .then((res) => {
        if (cancelled) return;
        setAllModels(res.models);
        const backends = Array.from(new Set(res.models.map((m) => m.backend)));
        if (backends.length > 0 && !backend) {
          const b = backends[0];
          setBackend(b);
          const models = res.models.filter((m) => m.backend === b);
          const def = models.find((m) => m.model_info?._ui?.default_model) ?? models[0];
          if (def) setModel(def.id);
        }
      })
      .finally(() => { if (!cancelled) setModelsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const backends = Array.from(new Set(allModels.map((m) => m.backend)));
  const models = allModels.filter((m) => m.backend === backend);

  const handleBackendChange = (b: string) => {
    setBackend(b);
    const filtered = allModels.filter((m) => m.backend === b);
    const def = filtered.find((m) => m.model_info?._ui?.default_model) ?? filtered[0];
    setModel(def?.id ?? "");
  };

  const handleNameChange = (value: string) => {
    setName(value);
    if (!slugTouched) setSlug(slugify(value));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !slug.trim() || !backend || !model) return;

    setSubmitting(true);
    setError("");
    try {
      const workflow = await workflowsApi.create({
        name: name.trim(),
        slug: slug.trim(),
        description: description.trim() || undefined,
        model_config: { backend, model },
      });
      router.push(routes.workflow(workflow.id));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create workflow";
      setError(msg);
      setSubmitting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-lg px-8 py-12">
        <Link
          href={routes.workflows}
          className="inline-flex items-center gap-1.5 type-caption text-fg-muted hover:text-fg-primary transition-colors"
        >
          <ArrowLeft size={12} strokeWidth={2} />
          Workflows
        </Link>
        <h1 className="mt-4 mb-8 type-heading text-fg-primary">New Workflow</h1>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="My Workflow"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="slug">Slug</Label>
              <Input
                id="slug"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); }}
                placeholder="my-workflow"
                pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this workflow do?"
              rows={3}
            />
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="backend">Backend</Label>
              <Select
                id="backend"
                value={backend}
                onChange={(e) => handleBackendChange(e.target.value)}
                disabled={modelsLoading}
              >
                {backends.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="model">Model</Label>
              <Select
                id="model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={modelsLoading}
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </Select>
            </div>
          </div>

          {error && <p className="type-caption text-danger">{error}</p>}

          <Button
            type="submit"
            variant="cta"
            disabled={submitting || !name.trim() || !slug.trim() || !backend || !model}
          >
            {submitting ? "Creating…" : "Create Workflow"}
          </Button>
        </form>
      </div>
    </div>
  );
}
