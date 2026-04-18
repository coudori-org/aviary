"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Trash2, AlertCircle } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { AgentDetailHero } from "@/features/agents/components/agent-detail-hero";
import { AgentRecentSessions } from "@/features/agents/components/agent-recent-sessions";
import { AgentConfigGrid } from "@/features/agents/components/agent-config-grid";
import { agentsApi } from "@/features/agents/api/agents-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { routes } from "@/lib/constants/routes";
import type { Agent, McpToolBinding } from "@/types";

/**
 * Agent detail page — dashboard for a single agent.
 *
 * Layout (top to bottom):
 *   1. Breadcrumb + edit/delete actions
 *   2. Deleted-banner if applicable
 *   3. Hero (icon, name, description, Start chat CTA)
 *   4. Recent Sessions (top 5 + view all)
 *   5. Configuration grid (model, identity, instruction, tools)
 *
 * The page itself is a thin assembler — each section is its own component
 * under features/agents/components/.
 */
export default function AgentDetailPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [mcpTools, setMcpTools] = useState<McpToolBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    Promise.all([agentsApi.get(params.id), agentsApi.getMcpTools(params.id)])
      .then(([agentData, bindings]) => {
        setAgent(agentData);
        setMcpTools(bindings);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [user, params.id]);

  if (loading) {
    return <LoadingState fullHeight label="Loading agent…" />;
  }

  if (error || !agent) {
    return (
      <div className="mx-auto max-w-container-sm p-8">
        <ErrorState title="Couldn't load agent" description={error || "Agent not found"} />
        <Link
          href={routes.agents}
          className="mt-4 inline-flex items-center gap-1.5 type-caption text-info hover:opacity-80"
        >
          <ArrowLeft size={12} strokeWidth={2} />
          Back to agents
        </Link>
      </div>
    );
  }

  const handleDelete = async () => {
    if (deleting) return;
    if (!confirm("Are you sure you want to delete this agent? This action cannot be undone.")) return;
    setDeleting(true);
    try {
      await agentsApi.remove(agent.id);
      router.push(routes.agents);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-container px-8 py-8">
        {/* Breadcrumb + actions */}
        <div className="mb-6 flex items-center justify-between">
          <Link
            href={routes.agents}
            className="inline-flex items-center gap-1.5 type-caption text-fg-muted hover:text-fg-primary transition-colors"
          >
            <ArrowLeft size={12} strokeWidth={2} />
            Agents
          </Link>
          <div className="flex items-center gap-2">
            <Link href={routes.agentEdit(agent.id)}>
              <Button variant="ghost" size="sm">
                Edit
              </Button>
            </Link>
            {agent.status !== "deleted" && (
              <Button variant="danger" size="sm" onClick={handleDelete} disabled={deleting}>
                <Trash2 size={13} strokeWidth={1.75} />
                {deleting ? "Deleting…" : "Delete"}
              </Button>
            )}
          </div>
        </div>

        {/* Deleted banner */}
        {agent.status === "deleted" && (
          <div className="mb-6 flex items-center gap-2.5 rounded-md border border-danger/20 bg-danger/[0.04] px-4 py-3">
            <AlertCircle size={14} strokeWidth={2} className="shrink-0 text-danger" />
            <span className="type-caption text-danger">
              This agent has been deleted. Existing sessions remain active, but no new sessions can be created.
            </span>
          </div>
        )}

        <AgentDetailHero agent={agent} />
        <AgentRecentSessions agentId={agent.id} />
        <AgentConfigGrid agent={agent} mcpTools={mcpTools} />
      </div>
    </div>
  );
}
