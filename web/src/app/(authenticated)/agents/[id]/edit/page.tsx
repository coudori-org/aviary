"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { AgentCrumb } from "@/features/agents/components/detail/agent-crumb";
import { AgentForm } from "@/features/agents/components/form/agent-form";
import { agentsApi } from "@/features/agents/api/agents-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { routes } from "@/lib/constants/routes";
import type { Agent, McpToolInfo } from "@/types";
import type { AgentFormData } from "@/features/agents/components/form/types";

export default function EditAgentPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [agent, setAgent] = React.useState<Agent | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [existingToolIds, setExistingToolIds] = React.useState<string[]>([]);
  const [existingToolInfo, setExistingToolInfo] = React.useState<Map<string, McpToolInfo>>(
    new Map(),
  );

  React.useEffect(() => {
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

  const crumb = React.useMemo(
    () => (agent ? <AgentCrumb agent={agent} trailing="Edit" /> : null),
    [agent],
  );
  usePageCrumb(crumb);

  if (loading) {
    return <LoadingState fullHeight label="Loading…" />;
  }

  if (error || !agent) {
    return (
      <ErrorState title="Couldn't load agent" description={error ?? "Agent not found."} />
    );
  }

  const handleSubmit = async (data: AgentFormData) => {
    const { mcp_tool_ids, ...agentData } = data;
    await agentsApi.update(agent.id, agentData);
    await agentsApi.setMcpTools(agent.id, mcp_tool_ids);
    router.push(routes.agentChat(agent.id));
  };

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mx-auto max-w-[820px]">
        <header className="mb-6">
          <h1 className="t-h1 fg-primary">Edit agent</h1>
          <p className="mt-1 t-small fg-tertiary">
            Update {agent.name}&apos;s configuration.
          </p>
        </header>
        <AgentForm
          initialData={{
            name: agent.name,
            slug: agent.slug,
            description: agent.description || "",
            instruction: agent.instruction,
            model_config: agent.model_config as AgentFormData["model_config"],
            tools: agent.tools as string[],
            mcp_tool_ids: existingToolIds,
          }}
          initialToolInfo={existingToolInfo}
          onSubmit={handleSubmit}
          submitLabel="Save changes"
          onCancel={() => router.push(routes.agentChat(agent.id))}
        />
      </div>
    </div>
  );
}
