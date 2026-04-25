"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight } from "@/components/icons";
import { AgentForm } from "@/features/agents/components/form/agent-form";
import { agentsApi } from "@/features/agents/api/agents-api";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { routes } from "@/lib/constants/routes";
import type { AgentFormData } from "@/features/agents/components/form/types";

export default function NewAgentPage() {
  const router = useRouter();

  const crumb = React.useMemo(() => <NewAgentCrumb />, []);
  usePageCrumb(crumb);

  const handleSubmit = async (data: AgentFormData) => {
    const { mcp_tool_ids, ...agentData } = data;
    const agent = await agentsApi.create(agentData);
    if (mcp_tool_ids.length > 0) {
      await agentsApi.setMcpTools(agent.id, mcp_tool_ids);
    }
    router.push(routes.agentChat(agent.id));
  };

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mx-auto max-w-[820px]">
        <header className="mb-6">
          <h1 className="t-h1 fg-primary">New agent</h1>
          <p className="mt-1 t-small fg-tertiary">
            Configure your agent&apos;s identity, behavior, model, and tools.
          </p>
        </header>
        <AgentForm
          onSubmit={handleSubmit}
          submitLabel="Create agent"
          onCancel={() => router.push(routes.agents)}
        />
      </div>
    </div>
  );
}

function NewAgentCrumb() {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex min-w-0 items-center gap-2 text-[12.5px]"
    >
      <Link href={routes.agents} className="text-fg-tertiary hover:text-fg-primary">
        Agents
      </Link>
      <ChevronRight size={11} className="text-fg-muted shrink-0" />
      <span className="truncate font-medium text-fg-primary">New agent</span>
    </nav>
  );
}
