"use client";

import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useEffect } from "react";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { usePreferences } from "@/features/auth/hooks/use-preferences";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { SortableAgentGroup } from "./sortable-agent-group";
import {
  orderGroupsByPreference,
  orderSessionsByPreference,
} from "@/features/layout/lib/sidebar-ordering";
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
 * grouped by their agent.
 *
 * Owns a single DndContext that handles BOTH levels of reordering:
 *   - Agent groups (top-level SortableContext at this component)
 *   - Sessions within an agent group (per-agent SortableContext nested
 *     inside SidebarAgentGroup; their drag events bubble up here)
 *
 * Each draggable tags itself via `data: { type: "agent" | "session", … }`
 * so this single drop handler can route to the right preference key.
 *
 * Reorder is persisted via `usePreferences` → PATCH /auth/me/preferences
 * with optimistic local updates so it survives logout / login / cross-device.
 *
 * Deleted agents are excluded from the sortable id list — they always
 * sit at the bottom and can't be reordered.
 */
export function SidebarSessions({ groups: groupsProp, searchActive }: SidebarSessionsProps) {
  const {
    groups: providerGroups,
    loading,
    collapsed,
    setVisibleSessionIds,
  } = useSidebar();
  const { preferences, updatePreferences } = usePreferences();
  const groups = groupsProp ?? providerGroups;

  // 5px distance lets clicks pass through; drag activates only after sustained movement.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // Scope collision detection so agents only collide with agents and sessions
  // only collide with sessions inside the same agent group — otherwise hovering
  // a dragged agent over a different group's session list cancels the drag.
  const collisionDetection: CollisionDetection = (args) => {
    const activeType = args.active.data.current?.type;
    const activeAgentId = args.active.data.current?.agentId;
    const scoped = args.droppableContainers.filter((c) => {
      const type = c.data.current?.type;
      if (type !== activeType) return false;
      if (activeType === "session") {
        return c.data.current?.agentId === activeAgentId;
      }
      return true;
    });
    return closestCenter({ ...args, droppableContainers: scoped });
  };

  const visibleGroups = groups.filter((g) => g.sessions.length > 0);
  const orderedGroups = orderGroupsByPreference(
    visibleGroups,
    preferences.sidebar_agent_order,
  );
  // Apply per-agent session ordering on top of the group ordering
  const orderedGroupsWithSortedSessions = orderedGroups.map((g) => ({
    ...g,
    sessions: orderSessionsByPreference(
      g.sessions,
      preferences.sidebar_session_order?.[g.agent.id],
    ),
  }));

  const totalSessions = groups.reduce((sum, g) => sum + g.sessions.length, 0);

  // Flat list of visible session ids in rendered order — drives
  // shift-range bulk selection in the sidebar provider. Must run
  // unconditionally (before any early return) to keep hook order stable.
  const visibleSessionIds = orderedGroupsWithSortedSessions.flatMap((g) =>
    g.sessions.map((s) => s.id),
  );
  const visibleKey = visibleSessionIds.join("|");
  useEffect(() => {
    setVisibleSessionIds(visibleSessionIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleKey, setVisibleSessionIds]);

  if (collapsed) return null;

  // Only non-deleted agents participate in the sortable id list
  const sortableAgentIds = orderedGroupsWithSortedSessions
    .filter((g) => g.agent.status !== "deleted")
    .map((g) => g.agent.id);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const activeType = active.data.current?.type;

    if (activeType === "agent") {
      const oldIndex = sortableAgentIds.indexOf(String(active.id));
      const newIndex = sortableAgentIds.indexOf(String(over.id));
      if (oldIndex === -1 || newIndex === -1) return;
      const newOrder = arrayMove(sortableAgentIds, oldIndex, newIndex);
      void updatePreferences({ sidebar_agent_order: newOrder });
      return;
    }

    if (activeType === "session") {
      const agentId = active.data.current?.agentId as string | undefined;
      if (!agentId) return;
      const group = orderedGroupsWithSortedSessions.find((g) => g.agent.id === agentId);
      if (!group) return;
      const ids = group.sessions.map((s) => s.id);
      const oldIndex = ids.indexOf(String(active.id));
      const newIndex = ids.indexOf(String(over.id));
      if (oldIndex === -1 || newIndex === -1) return;
      const newSessionOrder = arrayMove(ids, oldIndex, newIndex);
      void updatePreferences({
        sidebar_session_order: {
          ...(preferences.sidebar_session_order ?? {}),
          [agentId]: newSessionOrder,
        },
      });
    }
  };

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
      ) : orderedGroupsWithSortedSessions.length === 0 ? (
        <p className="px-3 type-caption text-fg-disabled">
          {searchActive ? "No matches" : "No active sessions"}
        </p>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={collisionDetection}
          onDragEnd={handleDragEnd}
        >
          <SortableContext items={sortableAgentIds} strategy={verticalListSortingStrategy}>
            <div className="space-y-1">
              {orderedGroupsWithSortedSessions.map(({ agent, sessions }) => (
                <SortableAgentGroup
                  key={agent.id}
                  agent={agent}
                  sessions={sessions}
                  sortable={agent.status !== "deleted"}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}
