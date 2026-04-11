"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "@/components/icons";
import { AgentForm } from "@/features/agents/components/form/agent-form";
import { agentsApi } from "@/features/agents/api/agents-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { routes } from "@/lib/constants/routes";
import type { Agent, McpToolInfo } from "@/types";
import type { AgentFormData } from "@/features/agents/components/form/types";

export default function EditAgentPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [existingToolIds, setExistingToolIds] = useState<string[]>([]);
  const [existingToolInfo, setExistingToolInfo] = useState<Map<string, McpToolInfo>>(new Map());

  useEffect(() => {
    if (!user) return;
    Promise.all([agentsApi.get(params.id), agentsApi.getMcpTools(params.id)])
      .then(([a, bindings]) => {
        setAgent(a);
        setExistingToolIds(bindings.map((b) => b.tool.id));
        const map = new Map<string, McpToolInfo>();
        for (const b of bindings) map.set(b.tool.id, b.tool);
        setExistingToolInfo(map);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [user, params.id]);

  if (loading) {
    return <LoadingState fullHeight label="Loading…" />;
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

  const handleSubmit = async (data: AgentFormData) => {
    const { mcp_tool_ids, ...agentData } = data;
    await agentsApi.update(agent.id, agentData);
    await agentsApi.setMcpTools(agent.id, mcp_tool_ids);
    router.push(routes.agent(agent.id));
  };

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-container-sm px-8 py-8">
        <Link
          href={routes.agent(agent.id)}
          className="inline-flex items-center gap-1.5 type-caption text-fg-muted hover:text-fg-primary transition-colors"
        >
          <ArrowLeft size={12} strokeWidth={2} />
          {agent.name}
        </Link>
        <h1 className="mt-4 type-heading text-fg-primary">Edit Agent</h1>
        <p className="mt-1 mb-8 type-caption text-fg-muted">
          Update {agent.name}&apos;s configuration
        </p>
        <AgentForm
          initialData={{
            name: agent.name,
            slug: agent.slug,
            description: agent.description || "",
            instruction: agent.instruction,
            model_config: agent.model_config as AgentFormData["model_config"],
            tools: agent.tools as string[],
            mcp_tool_ids: existingToolIds,
            visibility: agent.visibility,
            category: agent.category || "",
          }}
          initialToolInfo={existingToolInfo}
          onSubmit={handleSubmit}
          submitLabel="Save Changes"
        />
      </div>
    </div>
  );
}
