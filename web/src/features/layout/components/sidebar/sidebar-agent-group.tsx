"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { ChevronRight, Plus } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { useAgentStatus } from "@/features/layout/providers/agent-status-provider";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { useCreateSession } from "@/features/agents/hooks/use-create-session";
import { SortableSessionItem } from "./sortable-session-item";
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
 * The header shows:
 *   - chevron toggle (collapse/expand the nested session list)
 *   - agent icon + name (links to detail page)
 *   - hover-revealed `+` button (start new chat)
 *   - readiness dot OR "deleted" tag
 *
 * Collapsed state is per-agent, persisted via SidebarProvider's
 * `collapsedAgents` Set in localStorage. The chevron sits on the LEFT
 * of the row (before the icon) so it's a discoverable affordance and
 * doesn't fight with the existing right-side controls.
 *
 * Deleted agents render with strike-through, no `+` button — sessions
 * remain so users can still archive/resume them.
 */
export function SidebarAgentGroup({ agent, sessions }: SidebarAgentGroupProps) {
  const pathname = usePathname();
  const isActive = pathname.startsWith(`/agents/${agent.id}`);
  const readiness = useAgentStatus(agent.id);
  const isDeleted = agent.status === "deleted";
  const { createAndNavigate, creating } = useCreateSession(agent.id);
  const { collapsedAgents, toggleAgentCollapsed } = useSidebar();
  const isCollapsed = collapsedAgents.has(agent.id);

  const handleNewChat = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    void createAndNavigate();
  };

  const handleToggleCollapse = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    toggleAgentCollapsed(agent.id);
  };

  return (
    <div>
      <Link
        href={routes.agent(agent.id)}
        className={cn(
          "group/agent flex items-center gap-1.5 rounded-sm px-2 py-1.5 type-caption transition-colors",
          isActive ? "text-fg-primary" : "text-fg-muted hover:text-fg-primary",
        )}
      >
        {/* Collapse toggle — sits before the icon */}
        <button
          type="button"
          onClick={handleToggleCollapse}
          aria-label={isCollapsed ? `Expand ${agent.name}` : `Collapse ${agent.name}`}
          aria-expanded={!isCollapsed}
          className="flex h-4 w-4 shrink-0 items-center justify-center rounded-xs text-fg-disabled hover:text-fg-primary transition-colors"
        >
          <ChevronRight
            size={11}
            strokeWidth={2}
            className={cn("transition-transform", !isCollapsed && "rotate-90")}
          />
        </button>

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
            {creating ? <Spinner size={10} /> : <Plus size={11} strokeWidth={2.5} />}
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

      {!isCollapsed && (
        <div className="ml-5 space-y-0.5 border-l border-white/[0.06] pl-3">
          {/* Per-agent SortableContext lives inside the parent DndContext
              (in SidebarSessions). Drag events bubble up to that context's
              handler, which routes them via the `agentId` data tag. */}
          <SortableContext
            items={sessions.map((s) => s.id)}
            strategy={verticalListSortingStrategy}
          >
            {sessions.map((session) => (
              <SortableSessionItem
                key={session.id}
                session={session}
                isActive={pathname === routes.session(session.id)}
                agentId={agent.id}
              />
            ))}
          </SortableContext>
        </div>
      )}
    </div>
  );
}
