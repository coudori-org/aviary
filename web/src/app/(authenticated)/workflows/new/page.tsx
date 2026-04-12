"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { routes } from "@/lib/constants/routes";
import { slugify } from "@/lib/utils/format";

export default function NewWorkflowPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleNameChange = (value: string) => {
    setName(value);
    if (!slugTouched) setSlug(slugify(value));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !slug.trim()) return;

    setSubmitting(true);
    setError("");
    try {
      const workflow = await workflowsApi.create({
        name: name.trim(),
        slug: slug.trim(),
        description: description.trim() || undefined,
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
        <h1 className="mb-8 type-heading text-fg-primary">New Workflow</h1>

        <form onSubmit={handleSubmit} className="space-y-6">
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
            <p className="type-caption text-fg-muted">URL-safe identifier</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
            />
          </div>

          {error && <p className="type-caption text-danger">{error}</p>}

          <Button type="submit" variant="cta" disabled={submitting || !name.trim() || !slug.trim()}>
            {submitting ? "Creating…" : "Create Workflow"}
          </Button>
        </form>
      </div>
    </div>
  );
}
