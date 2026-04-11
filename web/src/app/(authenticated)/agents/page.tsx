"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Search } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AgentGrid } from "@/features/agents/components/agent-grid";
import { agentsApi } from "@/features/agents/api/agents-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { routes } from "@/lib/constants/routes";
import type { Agent } from "@/types";

/**
 * Agents list page — search + grid. The page itself is intentionally small;
 * AgentGrid handles the empty/loading states.
 */
export default function AgentsPage() {
  const { user } = useAuth();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    agentsApi
      .list(search || undefined)
      .then((data) => {
        setAgents(data.items.filter((a) => a.status !== "deleted" || a.owner_id === user.id));
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [user, search]);

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-container px-8 py-8">
        {/* Header */}
        <div className="mb-8 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="type-heading text-fg-primary">All Agents</h1>
            <p className="mt-1 type-caption text-fg-muted">
              {total} agent{total !== 1 ? "s" : ""} in your workspace
            </p>
          </div>
          <Link href={routes.agentNew}>
            <Button variant="cta">
              <Plus size={14} strokeWidth={2.5} />
              New Agent
            </Button>
          </Link>
        </div>

        {/* Search */}
        <div className="mb-6">
          <div className="relative max-w-md">
            <Search
              size={14}
              strokeWidth={1.75}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-disabled pointer-events-none"
            />
            <Input
              placeholder="Search agents…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        <AgentGrid
          agents={agents}
          loading={loading}
          searchActive={!!search}
          emptyAction={
            <Link href={routes.agentNew}>
              <Button variant="secondary" size="sm">
                Create your first agent
              </Button>
            </Link>
          }
        />
      </div>
    </div>
  );
}
