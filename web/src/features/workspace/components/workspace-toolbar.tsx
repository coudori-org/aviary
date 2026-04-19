"use client";

import { Eye, EyeOff, Minimize2, PanelRight, RefreshCw, X } from "@/components/icons";
import { cn } from "@/lib/utils";

interface WorkspaceToolbarProps {
  showHidden: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  onToggleHidden: () => void;
  onCollapseAll: () => void;
  onClosePanel: () => void;
  showExpandEditor: boolean;
  onExpandEditor: () => void;
}

export function WorkspaceToolbar({
  showHidden, refreshing, onRefresh, onToggleHidden, onCollapseAll, onClosePanel,
  showExpandEditor, onExpandEditor,
}: WorkspaceToolbarProps) {
  return (
    <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-2 py-1.5">
      <span className="type-caption font-semibold text-fg-muted uppercase tracking-wider px-1">
        Workspace
      </span>
      <div className="flex items-center gap-0.5">
        {showExpandEditor && (
          <ToolbarButton label="Open editor" onClick={onExpandEditor}>
            <PanelRight size={12} strokeWidth={2} className="shrink-0" />
          </ToolbarButton>
        )}
        <ToolbarButton
          label="Refresh"
          onClick={onRefresh}
          disabled={refreshing}
        >
          <RefreshCw
            size={12}
            strokeWidth={2}
            className={cn("shrink-0", refreshing && "animate-spin")}
          />
        </ToolbarButton>
        <ToolbarButton
          label={showHidden ? "Hide hidden files" : "Show hidden files"}
          onClick={onToggleHidden}
          active={showHidden}
        >
          {showHidden ? (
            <Eye size={12} strokeWidth={2} className="shrink-0" />
          ) : (
            <EyeOff size={12} strokeWidth={2} className="shrink-0" />
          )}
        </ToolbarButton>
        <ToolbarButton label="Collapse all" onClick={onCollapseAll}>
          <Minimize2 size={12} strokeWidth={2} className="shrink-0" />
        </ToolbarButton>
        <ToolbarButton label="Close workspace panel" onClick={onClosePanel}>
          <X size={12} strokeWidth={2} className="shrink-0" />
        </ToolbarButton>
      </div>
    </div>
  );
}

interface ToolbarButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  children: React.ReactNode;
}

function ToolbarButton({ label, onClick, disabled, active, children }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={cn(
        "flex h-6 w-6 items-center justify-center rounded-xs transition-colors",
        "text-fg-muted hover:bg-raised hover:text-fg-primary",
        "disabled:opacity-40 disabled:pointer-events-none",
        active && "bg-raised text-fg-primary",
      )}
    >
      {children}
    </button>
  );
}
