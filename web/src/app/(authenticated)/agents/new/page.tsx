"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { AgentForm } from "@/components/agents/agent-form";
import { apiFetch } from "@/lib/api";

export default function NewAgentPage() {
  const router = useRouter();

  const handleSubmit = async (data: any) => {
    const agent = await apiFetch<any>("/agents", {
      method: "POST",
      body: JSON.stringify(data),
    });
    router.push(`/agents/${agent.id}`);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-8">
        <Link href="/agents" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
          Back to agents
        </Link>
        <h1 className="mt-4 mb-2 text-xl font-bold text-foreground">Create New Agent</h1>
        <p className="mb-8 text-sm text-muted-foreground">Configure your AI agent&apos;s behavior, model, and capabilities</p>
        <AgentForm onSubmit={handleSubmit} submitLabel="Create Agent" />
      </div>
    </div>
  );
}
