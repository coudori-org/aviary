"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, MessageSquare } from "@/components/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { agentsApi } from "@/features/agents/api/agents-api";
import { routes } from "@/lib/constants/routes";
import { formatShortDate } from "@/lib/utils/format";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface AgentRecentSessionsProps {
  agentId: string;
}

const RECENT_LIMIT = 5;

/**
 * AgentRecentSessions — top N recent sessions for an agent, with a
 * "View all" link to the full sessions page.
 *
 * Self-fetches because the SidebarProvider only knows about *active*
 * sessions (filtered for the sidebar list), and the detail page wants
 * to show the most recently used regardless of status.
 *
 * Empty state nudges the user toward the Start chat CTA in the hero
 * rather than rendering nothing.
 */
export function AgentRecentSessions({ agentId }: AgentRecentSessionsProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    agentsApi
      .listSessions(agentId)
      .then((res) => {
        if (cancelled) return;
        // Sort newest first by created_at, take top N
        const sorted = [...res.items].sort((a, b) =>
          b.created_at.localeCompare(a.created_at),
        );
        setSessions(sorted.slice(0, RECENT_LIMIT));
        setTotal(res.items.length);
      })
      .catch(() => {
        // Non-fatal: detail page works without recent sessions section
        if (!cancelled) {
          setSessions([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  return (
    <section className="mb-8">
      <div className="mb-3 flex items-end justify-between">
        <h2 className="type-button text-fg-primary">Recent Sessions</h2>
        {total > RECENT_LIMIT && (
          <Link
            href={routes.agentSessions(agentId)}
            className="inline-flex items-center gap-1 type-caption text-fg-muted hover:text-brand transition-colors"
          >
            View all {total}
            <ArrowRight size={11} strokeWidth={2} />
          </Link>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-md" />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <div className="rounded-md border border-dashed border-border-subtle px-4 py-6 text-center">
          <MessageSquare size={18} strokeWidth={1.5} className="mx-auto text-fg-disabled" />
          <p className="mt-2 type-caption text-fg-muted">
            No conversations yet — use Start chat above to begin.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {sessions.map((session) => (
            <li key={session.id}>
              <Link
                href={routes.session(session.id)}
                className={cn(
                  "group flex items-center gap-3 rounded-md bg-elevated shadow-2 px-4 py-3",
                  "transition-colors duration-200 hover:bg-hover",
                )}
              >
                <MessageSquare
                  size={14}
                  strokeWidth={1.75}
                  className="shrink-0 text-fg-muted group-hover:text-brand transition-colors"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate type-body-tight text-fg-primary group-hover:text-brand transition-colors">
                    {session.title || "Untitled Session"}
                  </p>
                  <p className="mt-0.5 type-caption text-fg-muted">
                    {formatShortDate(session.created_at)}
                  </p>
                </div>
                <ArrowRight
                  size={12}
                  strokeWidth={2}
                  className="shrink-0 text-fg-disabled group-hover:text-brand transition-colors"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
