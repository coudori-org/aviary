"use client";

import Link from "next/link";
import { ArrowLeft, Trash2, Loader2, Upload, Pencil } from "@/components/icons";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

function ToolbarButton({
  onClick,
  disabled,
  title,
  children,
  danger,
}: {
  onClick: () => void;
  disabled?: boolean;
  title: string;
  children: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "flex items-center justify-center rounded-md px-2 py-1.5 text-[12px] font-medium transition-colors",
        disabled
          ? "text-fg-disabled cursor-not-allowed"
          : danger
            ? "text-fg-muted hover:text-danger hover:bg-danger/[0.06]"
            : "text-fg-muted hover:text-fg-primary hover:bg-white/[0.04]",
      )}
    >
      {children}
    </button>
  );
}

interface ToolbarProps {
  workflowStatus: string;
  deploying: boolean;
  onDeploy: () => void;
  onEdit: () => void;
}

export function Toolbar({ workflowStatus, deploying, onDeploy, onEdit }: ToolbarProps) {
  const { workflowName, undo, redo, canUndo, canRedo, deleteSelected } = useWorkflowBuilder();
  const isDraft = workflowStatus === "draft";

  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] bg-[rgb(10_11_13)] px-2 py-1.5">
      <div className="flex items-center gap-1">
        <Link
          href={routes.workflows}
          className="flex items-center justify-center rounded-md p-1.5 text-fg-muted hover:text-fg-primary hover:bg-white/[0.04] transition-colors"
        >
          <ArrowLeft size={16} strokeWidth={1.75} />
        </Link>
        <div className="mx-1 h-4 w-px bg-white/[0.06]" />
        <span className="text-[13px] font-medium text-fg-primary">{workflowName}</span>
        <span className={cn(
          "ml-2 rounded-sm px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
          isDraft ? "bg-warning/10 text-warning" : "bg-success/10 text-success",
        )}>
          {workflowStatus}
        </span>
      </div>

      <div className="flex items-center gap-0.5">
        {isDraft && (
          <>
            <ToolbarButton onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)">
              Undo
            </ToolbarButton>
            <ToolbarButton onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Shift+Z)">
              Redo
            </ToolbarButton>
            <div className="mx-1 h-4 w-px bg-white/[0.06]" />
            <ToolbarButton onClick={deleteSelected} title="Delete selected" danger>
              <Trash2 size={14} strokeWidth={1.75} />
            </ToolbarButton>
            <div className="mx-1 h-4 w-px bg-white/[0.06]" />
          </>
        )}

        {isDraft ? (
          <button
            type="button"
            onClick={onDeploy}
            disabled={deploying}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium bg-success/10 text-success hover:bg-success/20 transition-colors disabled:opacity-50"
          >
            {deploying ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} strokeWidth={2} />}
            {deploying ? "Deploying…" : "Deploy"}
          </button>
        ) : (
          <button
            type="button"
            onClick={onEdit}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium bg-info/10 text-info hover:bg-info/20 transition-colors"
          >
            <Pencil size={13} strokeWidth={2} />
            Edit
          </button>
        )}
      </div>
    </div>
  );
}
