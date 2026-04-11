"use client";

import { AgentCard } from "./agent-card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/feedback/empty-state";
import { Bot } from "@/components/icons";
import type { Agent } from "@/types";

interface AgentGridProps {
  agents: Agent[];
  loading: boolean;
  emptyAction?: React.ReactNode;
  searchActive?: boolean;
}

/**
 * AgentGrid — handles the three list states (loading, empty, populated)
 * and groups deleted agents into a separate "Archived" section below.
 */
export function AgentGrid({ agents, loading, emptyAction, searchActive }: AgentGridProps) {
  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-44 rounded-lg" />
        ))}
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <EmptyState
        icon={<Bot size={20} strokeWidth={1.5} />}
        title={searchActive ? "No agents match your search" : "No agents yet"}
        description={searchActive ? "Try a different keyword." : "Create your first agent to get started."}
        action={!searchActive ? emptyAction : undefined}
      />
    );
  }

  const active = agents.filter((a) => a.status !== "deleted");
  const deleted = agents.filter((a) => a.status === "deleted");

  return (
    <>
      {active.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {active.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      )}

      {deleted.length > 0 && (
        <div className={active.length > 0 ? "mt-10" : ""}>
          <h2 className="mb-4 type-small text-fg-disabled">Archived</h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {deleted.map((agent) => (
              <AgentCard key={agent.id} agent={agent} deleted />
            ))}
          </div>
        </div>
      )}
    </>
  );
}
