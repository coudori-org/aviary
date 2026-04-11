import * as React from "react";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

interface LoadingStateProps {
  label?: string;
  className?: string;
  /** Use full-screen height */
  fullHeight?: boolean;
}

function LoadingState({ label = "Loading…", className, fullHeight }: LoadingStateProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-center gap-3 text-fg-muted",
        fullHeight ? "h-full" : "py-16",
        className,
      )}
    >
      <Spinner size={16} />
      <span className="type-caption">{label}</span>
    </div>
  );
}

export { LoadingState };
