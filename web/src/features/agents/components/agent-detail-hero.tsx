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
        <div className="relative shrink-0">
          <div
            className={cn(
              "flex h-16 w-16 items-center justify-center rounded-xl glass-raised shadow-2 text-3xl",
              isDeleted && "grayscale",
            )}
          >
            {agent.icon || "🤖"}
          </div>
          {!isDeleted && (
            <div
              aria-hidden="true"
              className="absolute inset-0 -z-10 rounded-xl bg-aurora-a blur-2xl opacity-30"
            />
          )}
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
                "bg-aurora-a animate-aurora-sheen text-white",
                "shadow-[0_0_32px_rgba(123,92,255,0.4),inset_0_1px_0_rgba(255,255,255,0.2)]",
                "transition-all duration-[320ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
                "hover:-translate-y-[1px] hover:shadow-[0_0_44px_rgba(123,92,255,0.55),inset_0_1px_0_rgba(255,255,255,0.25)]",
                "disabled:opacity-60 disabled:cursor-not-allowed disabled:translate-y-0",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aurora-violet/50 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas",
              )}
            >
              {creating ? (
                <>
                  <Spinner size={14} className="text-white" />
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
