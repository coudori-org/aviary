"use client";

import { useRef } from "react";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { FormSection } from "./form-section";
import { MentionAutocomplete } from "@/features/chat/components/input/mention-autocomplete";
import type { AgentFormData } from "./types";

interface InstructionSectionProps {
  data: AgentFormData;
  setField: <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) => void;
}

export function InstructionSection({ data, setField }: InstructionSectionProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  return (
    <FormSection title="Behavior" description="Define how the agent should behave and respond">
      <div className="space-y-2">
        <Label htmlFor="agent-instruction">System Instruction</Label>
        <Textarea
          id="agent-instruction"
          ref={ref}
          value={data.instruction}
          onChange={(e) => setField("instruction", e.target.value)}
          placeholder="You are a helpful assistant that specializes in… (Type @ to reference another agent)"
          rows={8}
          className="font-mono type-code-sm"
        />
        <MentionAutocomplete
          textareaRef={ref}
          value={data.instruction}
          onChange={(v) => setField("instruction", v)}
          excludeSlug={data.slug}
        />
      </div>
    </FormSection>
  );
}
