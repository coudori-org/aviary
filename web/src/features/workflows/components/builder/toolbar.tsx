"use client";

import Link from "next/link";
import { ArrowLeft, Trash2, Loader2, Upload, Pencil, Workflow as WorkflowIcon } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { useWorkflowBuilder } from "@/features/workflows/providers/workflow-builder-provider";
import {
  useVersionSelection,
  DRAFT_SELECTION,
} from "@/features/workflows/providers/version-selection-provider";
import { routes } from "@/lib/constants/routes";
import { toneFromId } from "@/lib/tone";
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
          ? "text-fg-muted cursor-not-allowed"
          : danger
            ? "text-fg-muted hover:text-status-error hover:bg-status-error-soft"
            : "text-fg-muted hover:text-fg-primary hover:bg-hover",
      )}
    >
      {children}
    </button>
  );
}

interface ToolbarProps {
  deploying: boolean;
  deletingWorkflow: boolean;
  onDeploy: () => void;
  onEdit: () => void;
  onCancelEdit: () => void;
  onDeleteWorkflow: () => void;
}

export function Toolbar({
  deploying, deletingWorkflow, onDeploy, onEdit, onCancelEdit, onDeleteWorkflow,
}: ToolbarProps) {
  const { workflowId, workflowName, undo, redo, canUndo, canRedo, deleteSelected } = useWorkflowBuilder();
  const { versions, selected, isDraft, hasPriorDeploy, setSelected } = useVersionSelection();
  const latestId = versions[0]?.id;
  const tone = toneFromId(workflowId);

  return (
    <div className="flex items-center justify-between border-b border-border-subtle bg-canvas px-2 py-1.5">
      <div className="flex items-center gap-1">
        <Link
          href={routes.workflows}
          className="flex items-center justify-center rounded-md p-1.5 text-fg-muted hover:text-fg-primary hover:bg-hover transition-colors"
        >
          <ArrowLeft size={16} strokeWidth={1.75} />
        </Link>
        <div className="mx-1 h-4 w-px bg-border-subtle" />
        <Link
          href={routes.workflowDetail(workflowId)}
          className="group inline-flex items-center gap-2 rounded-md px-1.5 py-1 -my-1 transition-colors hover:bg-hover"
          title="Open workflow detail"
        >
          <Avatar tone={tone} size="sm">
            <WorkflowIcon size={11} />
          </Avatar>
          <span className="text-[13px] font-medium text-fg-primary group-hover:underline decoration-fg-muted underline-offset-2">
            {workflowName}
          </span>
        </Link>
        <span className={cn(
          "ml-2 rounded-sm px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
          isDraft ? "bg-status-warn-soft text-status-warn" : "bg-status-live-soft text-status-live",
        )}>
          {isDraft ? "draft" : "deployed"}
        </span>
        <div className="mx-1 h-4 w-px bg-border-subtle" />
        <button
          type="button"
          onClick={onDeleteWorkflow}
          disabled={deletingWorkflow}
          title="Delete workflow (removes all runs and artifacts)"
          className="flex items-center justify-center rounded-md p-1.5 text-fg-muted hover:text-status-error hover:bg-status-error-soft transition-colors disabled:opacity-50"
        >
          {deletingWorkflow ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Trash2 size={14} strokeWidth={1.75} />
          )}
        </button>
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
            <div className="mx-1 h-4 w-px bg-border-subtle" />
            <ToolbarButton onClick={deleteSelected} title="Delete selected" danger>
              <Trash2 size={14} strokeWidth={1.75} />
            </ToolbarButton>
            <div className="mx-1 h-4 w-px bg-border-subtle" />
          </>
        )}

        {(isDraft || versions.length > 0) && (
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="mr-1 rounded-md border border-border-default bg-raised px-2 py-1 text-[12px] text-fg-primary focus:outline-none focus:border-accent-border"
            title="Select version"
          >
            {isDraft && <option value={DRAFT_SELECTION}>Draft</option>}
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                v{v.version}
                {v.id === latestId ? " (latest)" : ""}
              </option>
            ))}
          </select>
        )}

        {isDraft && hasPriorDeploy && (
          <button
            type="button"
            onClick={onCancelEdit}
            className="mr-1 flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium text-fg-muted hover:text-status-error hover:bg-status-error-soft transition-colors"
            title="Discard draft changes and return to the latest deployed version"
          >
            Cancel
          </button>
        )}

        {isDraft ? (
          <button
            type="button"
            onClick={onDeploy}
            disabled={deploying}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium bg-status-live-soft text-status-live hover:bg-status-live/20 transition-colors disabled:opacity-50"
          >
            {deploying ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} strokeWidth={2} />}
            {deploying ? "Deploying…" : "Deploy"}
          </button>
        ) : (
          <button
            type="button"
            onClick={onEdit}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium bg-accent-soft text-accent hover:bg-accent/20 transition-colors"
          >
            <Pencil size={13} strokeWidth={2} />
            Edit
          </button>
        )}
      </div>
    </div>
  );
}
