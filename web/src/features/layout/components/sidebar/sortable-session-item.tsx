"use client";

import { useEffect, useRef } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { SidebarSessionItem } from "./sidebar-session-item";
import { cn } from "@/lib/utils";
import type { Session } from "@/types";

interface SortableSessionItemProps {
  session: Session;
  isActive: boolean;
  /** Parent agent ID — passed to dnd-kit `data` so the central drop
   *  handler knows which agent's session_order to update. */
  agentId: string;
}

/**
 * SortableSessionItem — thin sortable wrapper around SidebarSessionItem.
 *
 * Lives inside SidebarAgentGroup's per-agent SortableContext. Tags itself
 * with `type: "session"` and `agentId` so the parent DndContext (at
 * SidebarSessions) can route the drop event to the right reorder logic.
 *
 * Click suppression after drag: same `wasDragging` ref + capture-phase
 * click handler pattern as SortableAgentGroup. Without this, a drag
 * would still trigger navigation to the dropped session because the
 * inner Link's click handler fires on pointerup.
 */
export function SortableSessionItem({ session, isActive, agentId }: SortableSessionItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: session.id,
    data: { type: "session", agentId },
  });

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
      className={cn("cursor-grab", isDragging && "opacity-40 cursor-grabbing")}
      {...attributes}
      {...listeners}
      onClickCapture={handleClickCapture}
      onDragStart={(e) => e.preventDefault()}
    >
      <SidebarSessionItem session={session} isActive={isActive} />
    </div>
  );
}
