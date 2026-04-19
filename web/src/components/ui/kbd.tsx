import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Kbd — glass chip keyboard keycap. Light top edge + bottom shadow gives
 * it a soft physical feel without fighting the rest of the glass system.
 */
const Kbd = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <kbd
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5",
        "type-code-sm text-fg-secondary",
        "rounded-xs bg-white/[0.07] border border-white/[0.08]",
        "shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_1px_2px_rgba(0,0,0,0.3)]",
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
