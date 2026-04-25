import * as React from "react";
import { cn } from "@/lib/utils";

type Variant = "live" | "warn" | "error" | "info" | "idle";

const map: Record<Variant, { bg: string; halo: string }> = {
  live:  { bg: "bg-status-live",  halo: "shadow-[0_0_0_3px_var(--status-live-soft)]" },
  warn:  { bg: "bg-status-warn",  halo: "shadow-[0_0_0_3px_var(--status-warn-soft)]" },
  error: { bg: "bg-status-error", halo: "shadow-[0_0_0_3px_var(--status-error-soft)]" },
  info:  { bg: "bg-status-info",  halo: "shadow-[0_0_0_3px_var(--status-info-soft)]" },
  idle:  { bg: "bg-fg-muted",     halo: "" },
};

export interface StatusDotProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant: Variant;
  pulse?: boolean;
}

export function StatusDot({ variant, pulse, className, ...props }: StatusDotProps) {
  const { bg, halo } = map[variant];
  return (
    <span
      className={cn(
        "inline-block w-[6px] h-[6px] rounded-full",
        bg,
        halo,
        pulse && "animate-pulse",
        className
      )}
      {...props}
    />
  );
}
