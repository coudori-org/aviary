import * as React from "react";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}

function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-[10px]",
        "border border-status-error/30 bg-status-error-soft py-12 px-8 text-center",
        className,
      )}
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-status-error/20 text-status-error">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <div className="flex flex-col items-center gap-1">
        <p className="t-body text-fg-primary">{title}</p>
        {description && <p className="text-[12.5px] text-fg-muted max-w-md">{description}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 text-[12.5px] text-accent hover:opacity-80 transition-opacity"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export { ErrorState };
