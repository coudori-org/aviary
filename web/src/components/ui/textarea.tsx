import * as React from "react";
import { cn } from "@/lib/utils";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "flex min-h-[80px] w-full rounded-sm px-3.5 py-2.5 type-body-tight text-fg-primary",
      "bg-white/[0.04] border border-white/[0.08]",
      "transition-all duration-200 ease-out",
      "placeholder:text-fg-disabled",
      "hover:border-white/[0.14] hover:bg-white/[0.06]",
      "focus-visible:outline-none focus-visible:border-aurora-violet/50",
      "focus-visible:shadow-[0_0_0_3px_rgba(123,92,255,0.2),0_0_24px_rgba(123,92,255,0.25)]",
      "disabled:cursor-not-allowed disabled:opacity-40",
      "resize-y",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export { Textarea };
