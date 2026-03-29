"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Agent } from "@/types";

export default function AgentDetailPage() {
  const { user } = useAuth();
  const params = useParams();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<Agent>(`/agents/${params.id}`)
      .then(setAgent)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [user, params.id]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-muted-foreground">
          <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">Loading agent...</span>
        </div>
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="mx-auto max-w-3xl p-8">
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-5 text-sm text-destructive">
          {error || "Agent not found"}
        </div>
        <Link href="/agents" className="mt-4 inline-flex items-center gap-1 text-sm text-primary hover:underline">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
          Back to agents
        </Link>
      </div>
    );
  }

  const handleDelete = async () => {
    if (!confirm("Are you sure you want to delete this agent? This action cannot be undone.")) return;
    await apiFetch(`/agents/${agent.id}`, { method: "DELETE" });
    router.push("/agents");
  };

  const handleNewSession = async () => {
    const session = await apiFetch<any>(`/agents/${agent.id}/sessions`, {
      method: "POST",
      body: JSON.stringify({ type: "private" }),
    });
    router.push(`/sessions/${session.id}`);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-8 py-8">
        {/* Breadcrumb + actions */}
        <div className="mb-6 flex items-center justify-between">
          <Link href="/agents" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
            Agents
          </Link>
          <div className="flex items-center gap-2">
            <Link href={`/agents/${agent.id}/edit`}>
              <Button variant="ghost" size="sm">Edit</Button>
            </Link>
            <Link href={`/agents/${agent.id}/settings`}>
              <Button variant="ghost" size="sm">Settings</Button>
            </Link>
            <Button variant="destructive" size="sm" onClick={handleDelete}>
              Delete
            </Button>
          </div>
        </div>

        {/* Agent header */}
        <div className="mb-8 flex items-start gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 text-2xl">
            {agent.icon || "🤖"}
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-bold text-foreground">{agent.name}</h1>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {agent.description || "No description"}
            </p>
          </div>
        </div>

        {/* Info cards */}
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Model</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <InfoRow label="Backend" value={agent.model_config.backend} />
              <InfoRow label="Model" value={agent.model_config.model} mono />
              <InfoRow label="Temperature" value={String(agent.model_config.temperature)} />
              <InfoRow label="Max Tokens" value={String(agent.model_config.maxTokens)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <InfoRow label="Identifier" value={agent.slug} mono />
              <InfoRow label="Visibility" value={agent.visibility} capitalize />
              <InfoRow label="Status" value={agent.status} capitalize />
            </CardContent>
          </Card>

          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>System Instruction</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-lg bg-secondary/50 p-4 text-sm leading-relaxed text-foreground/80">
                <pre className="whitespace-pre-wrap font-sans">{agent.instruction}</pre>
              </div>
            </CardContent>
          </Card>

          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Tools</CardTitle>
            </CardHeader>
            <CardContent>
              {agent.tools.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {agent.tools.map((tool: string) => (
                    <span key={tool} className="rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-accent-foreground">
                      {tool}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No tools configured</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Quick actions */}
        <div className="mt-8 flex gap-3">
          <Button size="lg" className="flex-1" onClick={handleNewSession}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            New Chat
          </Button>
          <Link href={`/agents/${agent.id}/sessions`} className="flex-1">
            <Button size="lg" variant="outline" className="w-full">
              View All Sessions
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value, mono, capitalize: cap }: { label: string; value: string; mono?: boolean; capitalize?: boolean }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`text-foreground/90 ${mono ? "font-mono text-xs" : ""} ${cap ? "capitalize" : ""}`}>{value}</span>
    </div>
  );
}
