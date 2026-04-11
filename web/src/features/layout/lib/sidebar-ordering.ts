import type { Session } from "@/types";
import type { SidebarAgentGroup } from "@/features/layout/providers/sidebar-provider";

/**
 * Pure ordering helpers for the sidebar's "By Agent" view.
 *
 * Two rules combine to produce the final visual order:
 *
 *   1. Deleted agents always sink to the bottom regardless of any
 *      user-defined order. (SIDE-8)
 *   2. Within the active partition, items appear in the order recorded
 *      in `user.preferences.sidebar_agent_order`. Items not present in
 *      the stored order (e.g. newly created agents) sort after the
 *      ordered ones, preserving their original relative position. (SIDE-9)
 *
 * Same logic applies to sessions within an agent group.
 *
 * Pure functions, no React, fully unit-testable.
 */

export function orderGroupsByPreference(
  groups: SidebarAgentGroup[],
  agentOrder: string[] | undefined,
): SidebarAgentGroup[] {
  const active: SidebarAgentGroup[] = [];
  const deleted: SidebarAgentGroup[] = [];
  for (const g of groups) {
    if (g.agent.status === "deleted") deleted.push(g);
    else active.push(g);
  }
  return [
    ...applyUserOrder(active, agentOrder, (g) => g.agent.id),
    ...deleted,
  ];
}

export function orderSessionsByPreference(
  sessions: Session[],
  sessionOrder: string[] | undefined,
): Session[] {
  return applyUserOrder(sessions, sessionOrder, (s) => s.id);
}

/**
 * Stable sort: items present in `order` come first (in stored order),
 * items not present come after in their original relative order.
 */
function applyUserOrder<T>(
  items: T[],
  order: string[] | undefined,
  getId: (item: T) => string,
): T[] {
  if (!order || order.length === 0) return items;

  const orderMap = new Map<string, number>();
  order.forEach((id, idx) => orderMap.set(id, idx));

  // Decorate-sort-undecorate to preserve original relative order for ties
  return items
    .map((item, originalIdx) => ({ item, originalIdx, orderIdx: orderMap.get(getId(item)) }))
    .sort((a, b) => {
      const aHas = a.orderIdx !== undefined;
      const bHas = b.orderIdx !== undefined;
      if (aHas && bHas) return a.orderIdx! - b.orderIdx!;
      if (aHas) return -1;
      if (bHas) return 1;
      return a.originalIdx - b.originalIdx;
    })
    .map((entry) => entry.item);
}
