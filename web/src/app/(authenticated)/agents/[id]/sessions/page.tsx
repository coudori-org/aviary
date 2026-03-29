"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { Agent, Session } from "@/types";

export default function AgentSessionsPage() {
  const { user } = useAuth();
  const params = useParams();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      apiFetch<Agent>(`/agents/${params.id}`),
      apiFetch<{ items: Session[] }>(`/agents/${params.id}/sessions`).catch(() => ({ items: [] })),
    ]).then(([a, s]) => { setAgent(a); setSessions(s.items); }).catch(() => {}).finally(() => setLoading(false));
  }, [user, params.id]);

  if (loading || !agent) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-muted-foreground">
          <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
          <span className="text-sm">Loading...</span>
        </div>
      </div>
    );
  }

  const handleNewSession = async () => {
    const session = await apiFetch<Session>(`/agents/${agent.id}/sessions`, { method: "POST", body: JSON.stringify({ type: "private" }) });
    router.push(`/sessions/${session.id}`);
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-8">
        <Link href={`/agents/${agent.id}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
          {agent.name}
        </Link>
        <div className="mt-4 mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-foreground">Sessions</h1>
            <p className="mt-1 text-sm text-muted-foreground">{sessions.length} conversation{sessions.length !== 1 ? "s" : ""}</p>
          </div>
          <Button onClick={handleNewSession}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            New Session
          </Button>
        </div>

        {sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 py-16">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-secondary text-muted-foreground">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
            </div>
            <p className="mt-4 text-sm text-muted-foreground">No conversations yet</p>
            <Button onClick={handleNewSession} variant="outline" size="sm" className="mt-3">Start your first session</Button>
          </div>
        ) : (
          <div className="space-y-2">
            {sessions.map((session) => (
              <Link key={session.id} href={`/sessions/${session.id}`} className="group block rounded-xl border border-border/40 bg-card p-4 transition-all duration-200 hover:border-primary/30 hover:bg-card/80">
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground group-hover:text-primary transition-colors">{session.title || "Untitled Session"}</p>
                    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="capitalize">{session.type}</span>
                      <span className="text-border">·</span>
                      <span>{new Date(session.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
                    </div>
                  </div>
                  <span className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium ${session.status === "active" ? "bg-success/10 text-success" : "bg-secondary text-muted-foreground"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${session.status === "active" ? "bg-success" : "bg-muted-foreground/50"}`} />
                    {session.status}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
