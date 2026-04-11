"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { Skeleton } from "@/components/ui/skeleton";
import { SidebarSessionItem } from "./sidebar-session-item";
import { routes } from "@/lib/constants/routes";
import type { Agent, Session } from "@/types";
import type { SidebarAgentGroup } from "@/features/layout/providers/sidebar-provider";

/**
 * SidebarSessionsByDate — flat session list bucketed by recency.
 *
 * Used when SidebarProvider.viewMode === "date". Sessions are flattened
 * across all agents, sorted newest-first by `last_message_at` (falling
 * back to `created_at`), and grouped into 5 fixed buckets.
 *
 * Each row inherits the existing SidebarSessionItem (same delete /
 * streaming / unread handling) with an extra `agentIcon` prefix so the
 * user can still tell which agent each session belongs to.
 */

interface SidebarSessionsByDateProps {
  /** Filtered sidebar groups (from useSidebarSearch). Defaults to provider's full list. */
  groups?: SidebarAgentGroup[];
  searchActive?: boolean;
}

interface DatedSession {
  session: Session;
  agent: Agent;
  pivot: number; // ms timestamp used for sorting
}

const BUCKETS = ["Today", "Yesterday", "This week", "This month", "Older"] as const;
type Bucket = (typeof BUCKETS)[number];

export function SidebarSessionsByDate({ groups: groupsProp, searchActive }: SidebarSessionsByDateProps) {
  const { groups: providerGroups, loading, collapsed, setVisibleSessionIds } = useSidebar();
  const groups = groupsProp ?? providerGroups;
  const pathname = usePathname();

  // Flatten + sort newest first
  const dated: DatedSession[] = groups.flatMap((g) =>
    g.sessions.map((s) => ({
      session: s,
      agent: g.agent,
      pivot: new Date(s.last_message_at || s.created_at).getTime(),
    })),
  );
  dated.sort((a, b) => b.pivot - a.pivot);

  const buckets = bucketSessions(dated);
  const totalSessions = dated.length;

  // Push the flat rendered order to the provider so shift-range
  // selection can compute contiguous spans across buckets.
  const visibleSessionIds = (Object.values(buckets) as DatedSession[][])
    .flat()
    .map((d) => d.session.id);
  const visibleKey = visibleSessionIds.join("|");
  useEffect(() => {
    setVisibleSessionIds(visibleSessionIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleKey, setVisibleSessionIds]);

  if (collapsed) return null;

  if (loading) {
    return (
      <div className="px-3 pt-2 space-y-2">
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-6" />
        ))}
      </div>
    );
  }

  if (totalSessions === 0) {
    return (
      <div className="px-3 pt-2">
        <p className="px-3 type-caption text-fg-disabled">
          {searchActive ? "No matches" : "No active sessions"}
        </p>
      </div>
    );
  }

  return (
    <div className="px-3 pt-2 space-y-3">
      {BUCKETS.map((bucket) => {
        const items = buckets[bucket];
        if (items.length === 0) return null;
        return (
          <div key={bucket}>
            <div className="px-3 mb-1">
              <span className="type-small text-fg-disabled">{bucket}</span>
            </div>
            <div className="space-y-0.5">
              {items.map(({ session, agent }) => (
                <SidebarSessionItem
                  key={session.id}
                  session={session}
                  isActive={pathname === routes.session(session.id)}
                  agentIcon={agent.icon || "🤖"}
                  agentName={agent.name}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Place each session into one of the five buckets based on its pivot time.
 *
 * Boundary semantics:
 *   - Today:      pivot is on the current local calendar day
 *   - Yesterday:  pivot is on yesterday's calendar day
 *   - This week:  2-7 days before today (excludes today/yesterday)
 *   - This month: 8-30 days before today
 *   - Older:      more than 30 days before today
 */
function bucketSessions(dated: DatedSession[]): Record<Bucket, DatedSession[]> {
  const out: Record<Bucket, DatedSession[]> = {
    Today: [],
    Yesterday: [],
    "This week": [],
    "This month": [],
    Older: [],
  };

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 24 * 60 * 60 * 1000;
  const weekStart = todayStart - 7 * 24 * 60 * 60 * 1000;
  const monthStart = todayStart - 30 * 24 * 60 * 60 * 1000;

  for (const item of dated) {
    if (item.pivot >= todayStart) out.Today.push(item);
    else if (item.pivot >= yesterdayStart) out.Yesterday.push(item);
    else if (item.pivot >= weekStart) out["This week"].push(item);
    else if (item.pivot >= monthStart) out["This month"].push(item);
    else out.Older.push(item);
  }

  return out;
}
