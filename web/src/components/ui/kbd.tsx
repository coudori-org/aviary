import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Kbd — physical-feeling keyboard key cap.
 *
 * Uses the Level 4 multi-layer shadow + linear-gradient background to
 * simulate a 3D pressed key. Used in tooltips, command palette, and
 * shortcut hints throughout the app.
 */
const Kbd = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <kbd
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center min-w-[20px] h-[20px] px-1.5",
        "type-code-sm text-fg-secondary",
        "rounded-xs bg-keycap shadow-4",
        className,
      )}
      {...props}
    >
      {children}
    </kbd>
  ),
);
Kbd.displayName = "Kbd";

export { Kbd };
