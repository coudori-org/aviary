"use client";

import { ArrowRight, MessageSquare } from "@/components/icons";
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
 * Layout:
 *   [Big icon] [Name]
 *              [Description]
 *              [Start chat CTA]  ← primary action, flows under the copy
 *                                   so it never stacks under the red Delete
 *                                   button in the breadcrumb row.
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

          {!isDeleted && (
            <button
              type="button"
              onClick={() => void createAndNavigate()}
              disabled={creating}
              aria-label={`Start chat with ${agent.name}`}
              className={cn(
                "mt-5 inline-flex h-11 items-center gap-2 rounded-pill px-6 type-button",
                "bg-white/[0.92] text-fg-on-light shadow-3",
                "transition-colors hover:bg-white",
                "disabled:opacity-60 disabled:cursor-not-allowed",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40",
              )}
            >
              {creating ? (
                <>
                  <Spinner size={14} className="text-fg-on-light" />
                  Starting…
                </>
              ) : (
                <>
                  <MessageSquare size={14} strokeWidth={2} />
                  Start chat
                  <ArrowRight size={14} strokeWidth={2} />
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-danger/20 bg-danger/[0.04] px-3 py-2 type-caption text-danger" role="alert">
          {error}
        </div>
      )}
    </header>
  );
}
