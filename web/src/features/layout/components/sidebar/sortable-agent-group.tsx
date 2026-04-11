"use client";

import { useEffect, useRef } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { SidebarAgentGroup } from "./sidebar-agent-group";
import { cn } from "@/lib/utils";
import type { Agent, Session } from "@/types";

interface SortableAgentGroupProps {
  agent: Agent;
  sessions: Session[];
  /** When false (deleted agents), sortable behavior is disabled — drag
   *  handle is inactive so the deleted-at-bottom invariant is preserved. */
  sortable?: boolean;
}

/**
 * SortableAgentGroup — thin sortable wrapper around the visual
 * SidebarAgentGroup. Used by SidebarSessions inside its DndContext to
 * make agent groups draggable.
 *
 * Drag activation: a single DndContext at the SidebarSessions level uses
 * a 5px-distance constraint, so simple clicks on links / buttons inside
 * the row still navigate normally. Only sustained pointer movement
 * starts a drag.
 *
 * Click suppression: the post-drop click event (which would normally
 * fire on the inner Link and trigger navigation) is blocked via
 * `wasDragging` ref + capture-phase click handler. The ref is set as
 * soon as @dnd-kit reports `isDragging = true` and cleared on the
 * suppressed click.
 *
 * Disabled for deleted agents — they always stay at the bottom and
 * can't be reordered.
 */
export function SortableAgentGroup({ agent, sessions, sortable = true }: SortableAgentGroupProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: agent.id,
    data: { type: "agent" },
    disabled: !sortable,
  });

  // Track whether a drag has happened on this row so we can swallow the
  // synthetic click that fires on pointerup. Capture phase runs before
  // the inner Link's bubble-phase onClick.
  const wasDragging = useRef(false);
  useEffect(() => {
    if (isDragging) wasDragging.current = true;
  }, [isDragging]);

  const handleClickCapture = (e: React.MouseEvent) => {
    if (wasDragging.current) {
      e.preventDefault();
      e.stopPropagation();
      wasDragging.current = false;
    }
  };

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        sortable && "cursor-grab",
        isDragging && "opacity-40 cursor-grabbing",
      )}
      {...attributes}
      {...(sortable ? listeners : {})}
      onClickCapture={handleClickCapture}
      // Suppress native browser drag (e.g. dragging the agent page link)
      // so it doesn't fight with @dnd-kit's pointer-based sensors.
      onDragStart={(e) => e.preventDefault()}
    >
      <SidebarAgentGroup agent={agent} sessions={sessions} />
    </div>
  );
}
