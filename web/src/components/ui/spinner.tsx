import * as React from "react";
import { cn } from "@/lib/utils";

interface SpinnerProps extends React.SVGAttributes<SVGElement> {
  size?: number;
}

/**
 * Spinner — single source of truth for loading indicators.
 * Replaces the dozens of inline `<svg className="animate-spin">` blocks.
 */
function Spinner({ size = 16, className, ...props }: SpinnerProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={cn("animate-spin", className)}
      aria-hidden="true"
      {...props}
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

export { Spinner };
