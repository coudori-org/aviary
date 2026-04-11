"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormSection } from "./form-section";
import type { AgentFormData } from "./types";

interface BasicInfoSectionProps {
  data: AgentFormData;
  onNameChange: (name: string) => void;
  setField: <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) => void;
}

export function BasicInfoSection({ data, onNameChange, setField }: BasicInfoSectionProps) {
  return (
    <FormSection title="Basic Information" description="Name and identity for your agent">
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="agent-name">Name</Label>
          <Input
            id="agent-name"
            value={data.name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="e.g. Code Reviewer"
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="agent-slug">Slug</Label>
          <Input
            id="agent-slug"
            value={data.slug}
            onChange={(e) => setField("slug", e.target.value)}
            placeholder="code-reviewer"
            pattern="[a-z0-9][a-z0-9\-]*[a-z0-9]"
            required
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="agent-description">Description</Label>
        <Input
          id="agent-description"
          value={data.description}
          onChange={(e) => setField("description", e.target.value)}
          placeholder="A brief description of what this agent does"
        />
      </div>
    </FormSection>
  );
}
