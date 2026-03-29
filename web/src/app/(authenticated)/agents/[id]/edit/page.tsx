"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { AgentForm } from "@/components/agents/agent-form";
import { apiFetch } from "@/lib/api";
import type { Agent } from "@/types";

export default function EditAgentPage() {
  const { user } = useAuth();
  const params = useParams();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    apiFetch<Agent>(`/agents/${params.id}`)
      .then(setAgent)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user, params.id]);

  if (loading || !agent) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-muted-foreground">
          <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">Loading...</span>
        </div>
      </div>
    );
  }

  const handleSubmit = async (data: any) => {
    await apiFetch(`/agents/${agent.id}`, { method: "PUT", body: JSON.stringify(data) });
    router.push(`/agents/${agent.id}`);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-8">
        <Link href={`/agents/${agent.id}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
          {agent.name}
        </Link>
        <h1 className="mt-4 mb-2 text-xl font-bold text-foreground">Edit Agent</h1>
        <p className="mb-8 text-sm text-muted-foreground">Update {agent.name}&apos;s configuration</p>
        <AgentForm
          initialData={{
            name: agent.name, slug: agent.slug, description: agent.description || "",
            instruction: agent.instruction, model_config: agent.model_config as any,
            tools: agent.tools as string[], visibility: agent.visibility, category: agent.category || "",
          }}
          onSubmit={handleSubmit}
          submitLabel="Save Changes"
        />
      </div>
    </div>
  );
}
