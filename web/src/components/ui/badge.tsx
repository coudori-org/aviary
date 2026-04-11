import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Badge — compact pill for tags, status, categorization.
 * DESIGN.md: bg-raised, 6px radius, 14px font weight 500, 0px 6px padding.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 type-caption",
  {
    variants: {
      variant: {
        neutral: "bg-raised text-fg-primary",
        muted: "bg-white/[0.04] text-fg-muted",
        info: "bg-info/10 text-info ring-1 ring-inset ring-info/20",
        success: "bg-success/10 text-success ring-1 ring-inset ring-success/20",
        warning: "bg-warning/10 text-warning ring-1 ring-inset ring-warning/20",
        danger: "bg-danger/10 text-danger ring-1 ring-inset ring-danger/20",
        brand: "bg-brand/10 text-brand ring-1 ring-inset ring-brand/20",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, className }))} {...props} />;
}

export { Badge, badgeVariants };
