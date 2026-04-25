import * as React from "react";
import { cn } from "@/lib/utils";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[72px] w-full rounded-[7px] border border-border bg-sunk px-[10px] py-2 text-[13px]",
        "text-fg-primary placeholder:text-fg-muted resize-y",
        "transition-[background,border-color] duration-fast",
        "focus-visible:outline-none focus-visible:border-accent-border focus-visible:bg-raised",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Textarea.displayName = "Textarea";
