import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-[30px] w-full rounded-[7px] border border-border bg-sunk px-[10px] text-[13px]",
        "text-fg-primary placeholder:text-fg-muted",
        "transition-[background,border-color] duration-fast",
        "focus-visible:outline-none focus-visible:border-accent-border focus-visible:bg-raised",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "file:border-0 file:bg-transparent file:text-sm file:font-medium",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
