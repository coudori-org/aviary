"use client";

import { useState } from "react";
import { Sparkles } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { extractErrorMessage } from "@/lib/http";
import { cn } from "@/lib/utils";
import {
  agentAutocompleteApi,
  type AutocompleteResponse,
} from "@/features/agents/api/agent-autocomplete-api";
import type { AgentFormData } from "./types";

interface Props {
  data: AgentFormData;
  applyResult: (r: AutocompleteResponse) => void;
}

export function AutocompleteBanner({ data, applyResult }: Props) {
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const modelReady = Boolean(data.model_config.backend && data.model_config.model);
  const disabled = !modelReady || running;

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await agentAutocompleteApi.run({
        name: data.name,
        description: data.description,
        instruction: data.instruction,
        model_config: data.model_config,
        mcp_tool_ids: data.mcp_tool_ids,
        user_prompt: prompt.trim() || undefined,
      });
      applyResult(res);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <section
      className={cn(
        "rounded-[10px] border border-accent-border bg-accent-soft p-4 space-y-3"
      )}
    >
      <header className="flex items-start gap-3">
        <span
          className={cn(
            "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[7px]",
            "bg-accent text-white"
          )}
          aria-hidden
        >
          <Sparkles size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="t-h3 fg-primary">AI Auto-complete</h2>
          <p className="t-small fg-tertiary mt-0.5">
            Describe what you want (optional). The model fills in the system
            instruction and picks relevant tools for you.
          </p>
        </div>
      </header>

      <Textarea
        id="autocomplete-prompt"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="e.g. triage GitHub issues daily and summarize the open ones"
        rows={2}
        disabled={running}
      />

      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 t-small fg-tertiary">
          <span
            className={cn(
              "inline-block h-1.5 w-1.5 rounded-full",
              modelReady ? "bg-accent" : "bg-fg-muted"
            )}
            aria-hidden
          />
          {modelReady ? (
            <>
              <span>Using</span>
              <code className="t-mono text-fg-secondary">{data.model_config.model}</code>
            </>
          ) : (
            <span>Select a model first</span>
          )}
        </span>

        <button
          type="button"
          disabled={disabled}
          onClick={handleRun}
          className={cn(
            "inline-flex items-center gap-1.5 h-[30px] px-3 rounded-[7px]",
            "text-[12.5px] font-medium",
            "bg-accent text-white border border-accent",
            "transition-[background,border-color,opacity] duration-fast",
            "hover:bg-accent/90 hover:border-accent/90",
            "disabled:opacity-50 disabled:pointer-events-none",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-soft"
          )}
        >
          {running ? (
            <>
              <Spinner size={11} className="text-white" />
              Generating…
            </>
          ) : (
            <>
              <Sparkles size={12} />
              Auto-complete
            </>
          )}
        </button>
      </div>

      {error && (
        <p
          className="rounded-[7px] border border-status-error bg-status-error-soft px-3 py-2 text-[12px] text-status-error"
          role="alert"
        >
          {error}
        </p>
      )}
    </section>
  );
}
