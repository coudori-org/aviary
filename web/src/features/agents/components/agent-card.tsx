"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { useCreateSession } from "@/features/agents/hooks/use-create-session";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types";

interface AgentCardProps {
  agent: Agent;
  deleted?: boolean;
}

const VISIBILITY_VARIANTS: Record<Agent["visibility"], "success" | "warning" | "muted"> = {
  public: "success",
  team: "warning",
  private: "muted",
};

const VISIBILITY_LABELS: Record<Agent["visibility"], string> = {
  public: "Public",
  team: "Team",
  private: "Private",
};

/**
 * AgentCard — single tile in the agents grid.
 *
 * Click semantics:
 *   - Card body  → agent detail page (browse / resume existing sessions)
 *   - Start chat → creates a new session and routes to /sessions/{id}
 *
 * The "Start chat" button suppresses the wrapping Link's navigation via
 * preventDefault + stopPropagation. This is the conventional pattern for
 * "secondary action inside a clickable card" even though button-inside-link
 * is technically invalid HTML; browsers tolerate it and the alternative
 * (giving up middle-click → new tab on the card) is worse UX.
 *
 * Session creation lifecycle is shared with the detail-page hero CTA and
 * the sidebar "+" button via the `useCreateSession` hook.
 *
 * Deleted agents only show the detail affordance — new sessions cannot
 * be created against them.
 */
export function AgentCard({ agent, deleted }: AgentCardProps) {
  const { createAndNavigate, creating, error } = useCreateSession(agent.id);

  const handleStartChat = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    void createAndNavigate();
  };

  return (
    <Link href={routes.agent(agent.id)} className="group block">
      <article
        className={cn(
          "relative flex h-full flex-col rounded-lg p-5 transition-all duration-200",
          "bg-elevated shadow-2",
          deleted ? "opacity-50 hover:opacity-70" : "hover:glow-warm",
        )}
      >
        {/* Header */}
        <div className="mb-3 flex items-start justify-between gap-2">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-lg",
                deleted ? "bg-raised grayscale" : "bg-raised",
              )}
            >
              {agent.icon || "🤖"}
            </div>
            <div className="min-w-0">
              <h3
                className={cn(
                  "type-body truncate transition-colors",
                  deleted
                    ? "text-fg-muted line-through decoration-fg-disabled"
                    : "text-fg-primary group-hover:text-brand",
                )}
              >
                {agent.name}
              </h3>
              <p className="type-caption text-fg-muted">
                {agent.model_config?.backend}
              </p>
            </div>
          </div>

          {deleted ? (
            <Badge variant="danger">Deleted</Badge>
          ) : (
            <Badge variant={VISIBILITY_VARIANTS[agent.visibility]}>
              {VISIBILITY_LABELS[agent.visibility]}
            </Badge>
          )}
        </div>

        {/* Description */}
        <p className="mb-4 line-clamp-2 flex-1 type-body-tight text-fg-muted">
          {agent.description || "No description provided"}
        </p>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-white/[0.06] pt-3">
          {agent.category ? (
            <Badge variant="muted">{agent.category}</Badge>
          ) : (
            <span />
          )}

          {deleted ? (
            <span className="type-caption text-fg-disabled">View sessions →</span>
          ) : (
            <button
              type="button"
              onClick={handleStartChat}
              disabled={creating}
              aria-label={`Start chat with ${agent.name}`}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 type-caption-bold",
                "border border-brand/30 bg-brand/[0.06] text-brand",
                "transition-colors",
                "hover:bg-brand/15 hover:border-brand/50",
                "disabled:opacity-60 disabled:cursor-not-allowed",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-1 focus-visible:ring-offset-elevated",
              )}
            >
              {creating ? (
                <>
                  <Spinner size={11} />
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

        {/* Inline error — stop click bubbling so it doesn't trigger card navigation */}
        {error && (
          <div
            className="mt-2 type-caption text-danger"
            role="alert"
            onClick={(e) => e.stopPropagation()}
          >
            {error}
          </div>
        )}
      </article>
    </Link>
  );
}
