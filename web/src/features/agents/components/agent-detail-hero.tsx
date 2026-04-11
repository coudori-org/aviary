"use client";

import { Spinner } from "@/components/ui/spinner";
import { useCreateSession } from "@/features/agents/hooks/use-create-session";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types";

interface AgentDetailHeroProps {
  agent: Agent;
}

/**
 * AgentDetailHero — top section of the agent detail page.
 *
 * Visual hierarchy:
 *   [Big icon] [Name + description]                  [Start chat CTA]
 *
 * The CTA is the primary action of the page — the whole detail page is
 * essentially a landing pad for "I want to chat with this agent".
 */
export function AgentDetailHero({ agent }: AgentDetailHeroProps) {
  const { createAndNavigate, creating, error } = useCreateSession(agent.id);
  const isDeleted = agent.status === "deleted";

  return (
    <header className="mb-8">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
        <div
          className={cn(
            "flex h-16 w-16 shrink-0 items-center justify-center rounded-xl bg-elevated shadow-2 text-3xl",
            isDeleted && "grayscale",
          )}
        >
          {agent.icon || "🤖"}
        </div>

        <div className="min-w-0 flex-1">
          <h1
            className={cn(
              "type-card-heading text-fg-primary",
              isDeleted && "line-through decoration-fg-disabled",
            )}
          >
            {agent.name}
          </h1>
          <p className="mt-1.5 type-body-tight text-fg-muted">
            {agent.description || "No description"}
          </p>
        </div>

        {!isDeleted && (
          <button
            type="button"
            onClick={() => void createAndNavigate()}
            disabled={creating}
            aria-label={`Start chat with ${agent.name}`}
            className={cn(
              "inline-flex h-11 shrink-0 items-center gap-2 rounded-md px-5 type-button",
              "border border-brand/30 bg-brand/[0.08] text-brand shadow-1",
              "transition-colors",
              "hover:bg-brand/15 hover:border-brand/50",
              "disabled:opacity-60 disabled:cursor-not-allowed",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
            )}
          >
            {creating ? (
              <>
                <Spinner size={14} />
                Starting…
              </>
            ) : (
              <>
                Start chat
                <span className="text-brand/60">↵</span>
              </>
            )}
          </button>
        )}
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-danger/20 bg-danger/[0.04] px-3 py-2 type-caption text-danger" role="alert">
          {error}
        </div>
      )}
    </header>
  );
}
