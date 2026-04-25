"use client";

import { useState } from "react";
import { Trash2, X, Check } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";

/**
 * SidebarBulkBar — floating toolbar shown when one or more sessions
 * are multi-selected via Shift+click in the sidebar.
 *
 * Two-step delete (click → "Click again to confirm") mirrors the
 * single-row delete pattern so the interaction feels consistent.
 */
export function SidebarBulkBar() {
  const { selectedSessionIds, clearSessionSelection, deleteSelectedSessions } =
    useSidebar();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const count = selectedSessionIds.size;
  if (count === 0) return null;

  const handleDelete = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setDeleting(true);
    try {
      await deleteSelectedSessions();
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  };

  const handleCancel = () => {
    setConfirming(false);
    clearSessionSelection();
  };

  return (
    <div
      className="mx-3 mt-2 flex items-center gap-2 rounded-sm border border-info/30 bg-info/10 px-2.5 py-1.5"
      onMouseLeave={() => setConfirming(false)}
    >
      <span className="flex-1 type-caption text-fg-primary">
        {count} selected
      </span>
      <button
        type="button"
        onClick={handleDelete}
        disabled={deleting}
        className="flex h-6 items-center gap-1 rounded-xs px-2 type-caption text-danger hover:bg-danger/10 disabled:opacity-50 transition-colors"
        title={confirming ? "Click again to confirm" : "Delete selected"}
        aria-label={confirming ? "Confirm delete" : "Delete selected"}
      >
        {deleting ? (
          <Spinner size={11} />
        ) : confirming ? (
          <Check size={11} strokeWidth={2.5} />
        ) : (
          <Trash2 size={11} strokeWidth={1.75} />
        )}
        {confirming ? "Confirm" : "Delete"}
      </button>
      <button
        type="button"
        onClick={handleCancel}
        className="flex h-6 w-6 items-center justify-center rounded-xs text-fg-muted hover:bg-hover hover:text-fg-primary transition-colors"
        title="Cancel selection"
        aria-label="Cancel selection"
      >
        <X size={12} strokeWidth={2} />
      </button>
    </div>
  );
}
