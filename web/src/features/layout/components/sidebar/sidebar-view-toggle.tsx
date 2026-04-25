"use client";

import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { cn } from "@/lib/utils";

/**
 * SidebarViewToggle — segmented control to switch how the session list
 * is grouped.
 *
 * Modes:
 *   - "agent" — sessions nested under their agent (default)
 *   - "date"  — sessions flattened, bucketed by recency
 *
 * Persisted to localStorage by SidebarProvider so the choice survives
 * across page reloads.
 *
 * Hidden when the sidebar is collapsed (no room for a labelled toggle).
 */
export function SidebarViewToggle() {
  const { collapsed, viewMode, setViewMode } = useSidebar();

  if (collapsed) return null;

  return (
    <div className="px-3 pt-2">
      <div
        role="tablist"
        aria-label="Sessions view mode"
        className="flex items-center gap-0 rounded-xs border border-border-subtle bg-canvas p-0.5"
      >
        <ToggleButton
          active={viewMode === "agent"}
          onClick={() => setViewMode("agent")}
          label="By agent"
        />
        <ToggleButton
          active={viewMode === "date"}
          onClick={() => setViewMode("date")}
          label="By date"
        />
      </div>
    </div>
  );
}

function ToggleButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "flex-1 rounded-xs px-2 py-1 type-caption text-center transition-colors",
        active
          ? "bg-raised text-fg-primary"
          : "text-fg-muted hover:text-fg-primary",
      )}
    >
      {label}
    </button>
  );
}
