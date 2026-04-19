import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Badge — Aurora Glass.
 *
 * Soft glass pill with intent-tinted wash. The `brand` variant uses the
 * aurora-A gradient for status markers that should stand out (e.g. Beta,
 * Featured).
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-pill px-2 py-0.5 type-caption",
  {
    variants: {
      variant: {
        neutral: "bg-white/[0.07] text-fg-primary ring-1 ring-inset ring-white/10",
        muted: "bg-white/[0.04] text-fg-muted ring-1 ring-inset ring-white/[0.06]",
        info: "bg-aurora-cyan/12 text-aurora-cyan ring-1 ring-inset ring-aurora-cyan/25",
        success: "bg-aurora-mint/12 text-aurora-mint ring-1 ring-inset ring-aurora-mint/25",
        warning: "bg-aurora-gold/14 text-aurora-gold ring-1 ring-inset ring-aurora-gold/25",
        danger: "bg-aurora-pink/12 text-aurora-pink ring-1 ring-inset ring-aurora-pink/25",
        brand: [
          "bg-aurora-a text-white",
          "shadow-[0_0_16px_rgba(123,92,255,0.35),inset_0_1px_0_rgba(255,255,255,0.2)]",
        ].join(" "),
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
