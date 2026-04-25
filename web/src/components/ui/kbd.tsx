import * as React from "react";
import { cn } from "@/lib/utils";

export const Kbd = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <kbd
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center min-w-[18px] h-[18px] px-1",
        "rounded-[4px] bg-sunk border border-border text-fg-tertiary",
        "font-mono text-[10.5px] font-medium",
        className
      )}
      {...props}
    >
      {children}
    </kbd>
  )
);
Kbd.displayName = "Kbd";
