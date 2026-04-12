"use client";

import Link from "next/link";
import { ArrowLeft, Trash2 } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

export function Toolbar() {
  const { workflowName, undo, redo, canUndo, canRedo, deleteSelected } = useWorkflowBuilder();

  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] bg-canvas px-3 py-2">
      <div className="flex items-center gap-3">
        <Link href={routes.workflows}>
          <Button variant="ghost" size="icon">
            <ArrowLeft size={16} strokeWidth={1.75} />
          </Button>
        </Link>
        <span className="type-body text-fg-primary">{workflowName}</span>
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={undo}
          disabled={!canUndo}
          className={cn(
            "rounded px-2 py-1 type-caption text-fg-muted transition-colors",
            canUndo ? "hover:bg-raised hover:text-fg-primary" : "opacity-40 cursor-not-allowed",
          )}
          title="Undo (Ctrl+Z)"
        >
          Undo
        </button>
        <button
          type="button"
          onClick={redo}
          disabled={!canRedo}
          className={cn(
            "rounded px-2 py-1 type-caption text-fg-muted transition-colors",
            canRedo ? "hover:bg-raised hover:text-fg-primary" : "opacity-40 cursor-not-allowed",
          )}
          title="Redo (Ctrl+Shift+Z)"
        >
          Redo
        </button>
        <div className="mx-1 h-4 w-px bg-white/[0.06]" />
        <Button variant="ghost" size="icon" onClick={deleteSelected} title="Delete selected">
          <Trash2 size={14} strokeWidth={1.75} />
        </Button>
      </div>
    </div>
  );
}
