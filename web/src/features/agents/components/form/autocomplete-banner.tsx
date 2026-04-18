"use client";

import { useState } from "react";
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
        "relative overflow-hidden rounded-lg p-5 space-y-4",
        "border border-info/40 bg-gradient-to-br from-info/[0.14] via-info/[0.06] to-info/[0.02]",
        running ? "glow-info" : "shadow-2",
        "transition-shadow duration-300",
      )}
    >
      {/* decorative top gradient bar — signature genAI accent */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 h-px",
          "bg-gradient-to-r from-transparent via-info/90 to-transparent",
          running && "animate-pulse-soft",
        )}
      />

      {/* soft glow blob behind the header for genAI vibe */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-16 -right-16 h-40 w-40 rounded-full bg-info/35 blur-3xl"
      />

      <header className="relative flex items-start gap-3">
        <span
          className={cn(
            "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
            "bg-info/25 text-info shadow-1",
            running && "animate-pulse-soft",
          )}
          aria-hidden
        >
          <SparkleIcon />
        </span>
        <div className="min-w-0">
          <h2 className="type-button bg-gradient-to-r from-fg-primary via-info to-fg-primary bg-clip-text text-transparent">
            AI Auto-complete
          </h2>
          <p className="type-caption text-fg-muted mt-0.5">
            Describe what you want (optional). The model fills in the system instruction
            and picks relevant tools for you.
          </p>
        </div>
      </header>

      <Textarea
        id="autocomplete-prompt"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="e.g. “triage GitHub issues daily and summarize the open ones”"
        rows={2}
        disabled={running}
        className="relative bg-canvas/60 backdrop-blur-sm focus-visible:border-info focus-visible:ring-info/40"
      />

      <div className="relative flex items-center justify-between gap-3">
        <span className="type-caption text-fg-muted inline-flex items-center gap-1.5">
          <span
            className={cn(
              "inline-block h-1.5 w-1.5 rounded-full",
              modelReady ? "bg-info shadow-[0_0_6px_rgb(var(--intent-info))]" : "bg-fg-disabled",
            )}
          />
          {modelReady ? (
            <>
              <span className="text-fg-muted">Using</span>
              <code className="type-code-sm text-fg-secondary">
                {data.model_config.model}
              </code>
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
            "inline-flex items-center gap-2 rounded-pill px-4 h-9 type-button",
            "border border-info/55 bg-info/25 text-info",
            "transition-[background,border-color,opacity,transform] duration-150",
            "hover:bg-info/35 hover:border-info/70",
            "active:scale-[0.98]",
            "disabled:opacity-40 disabled:pointer-events-none",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info/50 focus-visible:ring-offset-1 focus-visible:ring-offset-canvas",
          )}
        >
          {running ? (
            <>
              <Spinner size={12} />
              Generating…
            </>
          ) : (
            <>
              <SparkleIcon size={12} />
              Auto-complete
            </>
          )}
        </button>
      </div>

      {error && (
        <p
          className="relative rounded-md border border-danger/30 bg-danger/[0.04] p-2.5 type-caption text-danger"
          role="alert"
        >
          {error}
        </p>
      )}
    </section>
  );
}

function SparkleIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 2l1.76 5.34L19 9l-5.24 1.66L12 16l-1.76-5.34L5 9l5.24-1.66L12 2z" />
      <path
        d="M19 14l.88 2.67L22 17.5l-2.12.83L19 21l-.88-2.67L16 17.5l2.12-.83L19 14z"
        opacity="0.6"
      />
    </svg>
  );
}
