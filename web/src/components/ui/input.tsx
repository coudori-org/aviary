import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Input — Raycast dark surface, focus-blue glow.
 *
 * Background is the canvas color (not elevated) so inputs feel "carved in"
 * rather than floating. Focus replaces border with info-blue and adds glow.
 */
const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-9 w-full rounded-md bg-canvas px-3 type-body-tight text-fg-primary",
        "border border-white/[0.08] transition-colors duration-150",
        "placeholder:text-fg-disabled",
        "hover:border-white/[0.12]",
        "focus-visible:outline-none focus-visible:border-info focus-visible:ring-1 focus-visible:ring-info/30",
        "disabled:cursor-not-allowed disabled:opacity-40",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
