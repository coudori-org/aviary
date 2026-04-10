"use client";

import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { SidebarAgentGroup } from "./sidebar-agent-group";
import type { SidebarAgentGroup as SidebarAgentGroupData } from "@/features/layout/providers/sidebar-provider";

interface SidebarSessionsProps {
  /** Groups to render — typically the search-filtered subset from the
   *  parent Sidebar. Falls back to the provider's full list if omitted. */
  groups?: SidebarAgentGroupData[];
  /** When the user has an active search query, the empty state copy
   *  changes to "No matches" instead of "No active sessions". */
  searchActive?: boolean;
}

/**
 * SidebarSessions — the section of the sidebar that lists active sessions
 * grouped by their agent. Hidden when the sidebar is collapsed.
 */
export function SidebarSessions({ groups: groupsProp, searchActive }: SidebarSessionsProps) {
  const { groups: providerGroups, loading, collapsed } = useSidebar();
  const groups = groupsProp ?? providerGroups;

  if (collapsed) return null;

  const groupsWithSessions = groups.filter((g) => g.sessions.length > 0);
  const totalSessions = groups.reduce((sum, g) => sum + g.sessions.length, 0);

  return (
    <div className="px-3 pt-2">
      <div className="mb-2 flex items-center justify-between px-3">
        <span className="type-small text-fg-disabled">
          {searchActive ? "Sessions" : "Active Sessions"}
          {totalSessions > 0 && (
            <Badge variant="info" className="ml-2 px-1.5">
              {totalSessions}
            </Badge>
          )}
        </span>
      </div>

      {loading ? (
        <div className="space-y-2 px-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-6" />
          ))}
        </div>
      ) : groupsWithSessions.length === 0 ? (
        <p className="px-3 type-caption text-fg-disabled">
          {searchActive ? "No matches" : "No active sessions"}
        </p>
      ) : (
        <div className="space-y-1">
          {groupsWithSessions.map(({ agent, sessions }) => (
            <SidebarAgentGroup key={agent.id} agent={agent} sessions={sessions} />
          ))}
        </div>
      )}
    </div>
  );
}
