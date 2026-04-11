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
        "flex flex-col items-center justify-center gap-3 rounded-xl",
        "border border-dashed border-white/[0.06] py-20 px-8 text-center",
        className,
      )}
    >
      {icon && (
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-raised text-fg-muted">
          {icon}
        </div>
      )}
      <div className="flex flex-col items-center gap-1">
        <p className="type-body text-fg-primary">{title}</p>
        {description && <p className="type-caption text-fg-muted max-w-sm">{description}</p>}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export { EmptyState };
