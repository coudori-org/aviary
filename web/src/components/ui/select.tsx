import * as React from "react";
import { cn } from "@/lib/utils";

const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-sm px-3.5 type-body-tight text-fg-primary",
        "bg-hover border border-border",
        "transition-all duration-200 ease-out",
        "hover:border-border-strong hover:bg-hover",
        "focus-visible:outline-none focus-visible:border-accent/50",
        "focus-visible:shadow-[0_0_0_3px_rgba(123,92,255,0.2)]",
        "disabled:cursor-not-allowed disabled:opacity-40",
        // Native <option>s render in a browser popup with no backdrop, so a
        // translucent pane shows through as white. Force an opaque dark fill.
        "[&>option]:bg-canvas [&>option]:text-fg-primary",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  ),
);
Select.displayName = "Select";

export { Select };
