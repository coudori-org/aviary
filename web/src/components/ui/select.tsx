import * as React from "react";
import { cn } from "@/lib/utils";

const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-sm px-3.5 type-body-tight text-fg-primary",
        "bg-white/[0.04] border border-white/[0.08]",
        "transition-all duration-200 ease-out",
        "hover:border-white/[0.14] hover:bg-white/[0.06]",
        "focus-visible:outline-none focus-visible:border-aurora-violet/50",
        "focus-visible:shadow-[0_0_0_3px_rgba(123,92,255,0.2)]",
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
