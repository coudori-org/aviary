"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Plus, MessageSquare } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { EmptyState } from "@/components/feedback/empty-state";
import { agentsApi } from "@/features/agents/api/agents-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { routes } from "@/lib/constants/routes";
import { formatShortDate } from "@/lib/utils/format";
import type { Agent, Session } from "@/types";

export default function AgentSessionsPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    Promise.all([agentsApi.get(params.id), agentsApi.listSessions(params.id)])
      .then(([a, s]) => {
        setAgent(a);
        setSessions(s.items);
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
        <ErrorState title="Couldn't load sessions" description={error || "Agent not found"} />
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

  const handleNewSession = async () => {
    const session = await agentsApi.createSession(agent.id);
    router.push(routes.session(session.id));
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
        <div className="mt-4 mb-8 flex items-center justify-between">
          <div>
            <h1 className="type-heading text-fg-primary">Sessions</h1>
            <p className="mt-1 type-caption text-fg-muted">
              {sessions.length} conversation{sessions.length !== 1 ? "s" : ""}
            </p>
          </div>
          <Button variant="cta" onClick={handleNewSession} disabled={agent.status === "deleted"}>
            <Plus size={14} strokeWidth={2.5} />
            New Session
          </Button>
        </div>

        {sessions.length === 0 ? (
          <EmptyState
            icon={<MessageSquare size={20} strokeWidth={1.5} />}
            title="No conversations yet"
            description="Start your first session with this agent."
            action={
              <Button variant="secondary" size="sm" onClick={handleNewSession}>
                Start your first session
              </Button>
            }
          />
        ) : (
          <div className="space-y-2">
            {sessions.map((session) => (
              <Link
                key={session.id}
                href={routes.session(session.id)}
                className="group block rounded-md bg-elevated shadow-2 p-4 transition-all duration-200 hover:glow-warm"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate type-body text-fg-primary group-hover:text-brand transition-colors">
                      {session.title || "Untitled Session"}
                    </p>
                    <div className="mt-1 flex items-center gap-2 type-caption text-fg-muted">
                      <span className="capitalize">{session.type}</span>
                      <span className="text-fg-disabled">·</span>
                      <span>{formatShortDate(session.created_at)}</span>
                    </div>
                  </div>
                  <Badge variant={session.status === "active" ? "success" : "muted"}>
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        session.status === "active" ? "bg-success" : "bg-fg-disabled"
                      }`}
                    />
                    {session.status}
                  </Badge>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
