"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "@/components/icons";
import { AgentForm } from "@/features/agents/components/form/agent-form";
import { agentsApi } from "@/features/agents/api/agents-api";
import { routes } from "@/lib/constants/routes";
import type { AgentFormData } from "@/features/agents/components/form/types";

export default function NewAgentPage() {
  const router = useRouter();

  const handleSubmit = async (data: AgentFormData) => {
    const { mcp_tool_ids, ...agentData } = data;
    const agent = await agentsApi.create(agentData);

    if (mcp_tool_ids.length > 0) {
      await agentsApi.setMcpTools(agent.id, mcp_tool_ids);
    }
    router.push(routes.agent(agent.id));
  };

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-container-sm px-8 py-8">
        <Link
          href={routes.agents}
          className="inline-flex items-center gap-1.5 type-caption text-fg-muted hover:text-fg-primary transition-colors"
        >
          <ArrowLeft size={12} strokeWidth={2} />
          Back to agents
        </Link>
        <h1 className="mt-4 type-heading text-fg-primary">Create New Agent</h1>
        <p className="mt-1 mb-8 type-caption text-fg-muted">
          Configure your AI agent&apos;s behavior, model, and capabilities
        </p>
        <AgentForm onSubmit={handleSubmit} submitLabel="Create Agent" />
      </div>
    </div>
  );
}
