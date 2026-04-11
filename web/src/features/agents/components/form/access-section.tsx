"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { FormSection } from "./form-section";
import type { AgentFormData } from "./types";

interface AccessSectionProps {
  data: AgentFormData;
  setField: <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) => void;
}

export function AccessSection({ data, setField }: AccessSectionProps) {
  return (
    <FormSection
      title="Access & Organization"
      description="Control who can discover and use this agent"
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="agent-visibility">Visibility</Label>
          <Select
            id="agent-visibility"
            value={data.visibility}
            onChange={(e) => setField("visibility", e.target.value)}
          >
            <option value="private">Private — Only you</option>
            <option value="team">Team — Your team members</option>
            <option value="public">Public — Everyone</option>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="agent-category">Category</Label>
          <Input
            id="agent-category"
            value={data.category}
            onChange={(e) => setField("category", e.target.value)}
            placeholder="e.g. coding, writing, research"
          />
        </div>
      </div>
    </FormSection>
  );
}
