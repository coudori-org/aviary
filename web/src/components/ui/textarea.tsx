import * as React from "react";
import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "flex min-h-[80px] w-full rounded-md bg-canvas px-3 py-2.5 type-body-tight text-fg-primary",
      "border border-white/[0.08] transition-colors duration-150",
      "placeholder:text-fg-disabled",
      "hover:border-white/[0.12]",
      "focus-visible:outline-none focus-visible:border-info focus-visible:ring-1 focus-visible:ring-info/30",
      "disabled:cursor-not-allowed disabled:opacity-40",
      "resize-y",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export { Textarea };
