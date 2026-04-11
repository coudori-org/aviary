"use client";

import { useCallback, useState } from "react";
import { type AgentFormData, DEFAULT_AGENT_FORM_DATA } from "./types";
import { slugify } from "@/lib/utils/format";

/**
 * useAgentForm — encapsulates state, field updates, and slug auto-generation
 * for the agent create/edit form. Pure state management; submission is the
 * caller's responsibility (so the same hook works for create and edit).
 */
export function useAgentForm(initial?: Partial<AgentFormData>) {
  const [data, setData] = useState<AgentFormData>(() => {
    const merged = { ...DEFAULT_AGENT_FORM_DATA, ...initial };
    merged.model_config = { ...DEFAULT_AGENT_FORM_DATA.model_config, ...initial?.model_config };
    return merged;
  });

  const setField = useCallback(
    <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) => {
      setData((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const setModelConfig = useCallback(
    <K extends keyof AgentFormData["model_config"]>(
      key: K,
      value: AgentFormData["model_config"][K],
    ) => {
      setData((prev) => ({
        ...prev,
        model_config: { ...prev.model_config, [key]: value },
      }));
    },
    [],
  );

  const setName = useCallback(
    (name: string) => {
      setData((prev) => ({
        ...prev,
        name,
        // Only auto-fill slug for new agents (when initial.slug was not set)
        slug: initial?.slug ? prev.slug : slugify(name),
      }));
    },
    [initial?.slug],
  );

  return { data, setData, setField, setModelConfig, setName };
}
