import * as React from "react";
import { cn } from "@/lib/utils";

const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-md bg-canvas px-3 type-body-tight text-fg-primary",
        "border border-white/[0.08] transition-colors duration-150",
        "hover:border-white/[0.12]",
        "focus-visible:outline-none focus-visible:border-info focus-visible:ring-1 focus-visible:ring-info/30",
        "disabled:cursor-not-allowed disabled:opacity-40",
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
