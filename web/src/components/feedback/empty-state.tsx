import * as React from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

/**
 * EmptyState — single source of truth for "nothing to show" UI.
 *
 * Centered icon block, title, optional description, optional action.
 * Used by lists, search results, and any feature that can be empty.
 */
function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-[10px]",
        "border border-dashed border-border-subtle py-16 px-8 text-center",
        className,
      )}
    >
      {icon && (
        <div className="flex h-10 w-10 items-center justify-center rounded-[8px] bg-hover text-fg-tertiary">
          {icon}
        </div>
      )}
      <div className="flex flex-col items-center gap-1">
        <p className="t-body text-fg-primary">{title}</p>
        {description && <p className="text-[12.5px] text-fg-muted max-w-sm">{description}</p>}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export { EmptyState };
