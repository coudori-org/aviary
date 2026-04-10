"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plus } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { useAgentStatus } from "@/features/layout/providers/agent-status-provider";
import { useCreateSession } from "@/features/agents/hooks/use-create-session";
import { SidebarSessionItem } from "./sidebar-session-item";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import type { Agent, Session } from "@/types";

interface SidebarAgentGroupProps {
  agent: Agent;
  sessions: Session[];
}

/**
 * SidebarAgentGroup — header row for an agent + nested session list.
 *
 * The header shows agent icon, name, a readiness dot, and a hover-revealed
 * `+` button that creates a new session for this agent without leaving
 * the current page (uses the same `useCreateSession` hook as the agent
 * card and detail page CTA).
 *
 * Deleted agents render with strike-through, a "deleted" tag, and no
 * `+` button — new sessions can't be created against them.
 */
export function SidebarAgentGroup({ agent, sessions }: SidebarAgentGroupProps) {
  const pathname = usePathname();
  const isActive = pathname.startsWith(`/agents/${agent.id}`);
  const readiness = useAgentStatus(agent.id);
  const isDeleted = agent.status === "deleted";
  const { createAndNavigate, creating } = useCreateSession(agent.id);

  const handleNewChat = (e: React.MouseEvent) => {
    // Suppress the wrapping <Link>'s navigation to detail.
    e.preventDefault();
    e.stopPropagation();
    void createAndNavigate();
  };

  return (
    <div>
      <Link
        href={routes.agent(agent.id)}
        className={cn(
          "group/agent flex items-center gap-2 rounded-sm px-3 py-1.5 type-caption transition-colors",
          isActive ? "text-fg-primary" : "text-fg-muted hover:text-fg-primary",
        )}
      >
        <span className={cn("text-sm", isDeleted && "grayscale opacity-40")}>
          {agent.icon || "🤖"}
        </span>
        <span
          className={cn(
            "truncate flex-1",
            isDeleted && "text-fg-disabled line-through decoration-fg-disabled decoration-1",
          )}
        >
          {agent.name}
        </span>

        {/* Hover-revealed "+" — only for non-deleted agents */}
        {!isDeleted && (
          <button
            type="button"
            onClick={handleNewChat}
            disabled={creating}
            aria-label={`Start new chat with ${agent.name}`}
            title="New chat"
            className={cn(
              "flex h-4 w-4 shrink-0 items-center justify-center rounded-xs",
              "text-fg-muted hover:text-brand transition-colors",
              "opacity-0 group-hover/agent:opacity-100 focus-visible:opacity-100",
              creating && "opacity-100",
              "disabled:cursor-not-allowed",
            )}
          >
            {creating ? (
              <Spinner size={10} />
            ) : (
              <Plus size={11} strokeWidth={2.5} />
            )}
          </button>
        )}

        {isDeleted ? (
          <span className="shrink-0 text-[9px] text-danger/60">deleted</span>
        ) : (
          <span
            className={cn(
              "h-1.5 w-1.5 shrink-0 rounded-full",
              readiness === "ready" ? "bg-success" : "bg-fg-disabled/50",
            )}
            title={readiness === "ready" ? "Agent ready" : "Agent offline"}
            aria-label={readiness === "ready" ? "Agent ready" : "Agent offline"}
          />
        )}
      </Link>

      <div className="ml-5 space-y-0.5 border-l border-white/[0.06] pl-3">
        {sessions.map((session) => (
          <SidebarSessionItem
            key={session.id}
            session={session}
            isActive={pathname === routes.session(session.id)}
          />
        ))}
      </div>
    </div>
  );
}
