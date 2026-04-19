import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Card primitives — Aurora Glass.
 *
 * Every variant uses a translucent surface so the aurora backdrop bleeds
 * through. backdrop-blur is applied via the .glass-* utilities which
 * @supports-guard against backdrop-filter-less browsers.
 *
 * Variants:
 * - standard:    4% white glass, hairline border
 * - elevated:    7% glass with soft drop shadow (floating pane)
 * - feature:     elevated + violet glow for hero/featured content
 * - interactive: glass that lifts on hover
 */
const cardVariants = cva(
  "rounded-lg",
  {
    variants: {
      variant: {
        standard: "glass-pane",
        elevated: "glass-raised shadow-2",
        feature: "glass-raised shadow-3 glow-violet",
        interactive: [
          "glass-pane",
          "transition-all duration-[320ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
          "hover:-translate-y-[1px] hover:bg-white/[0.08] hover:shadow-3",
          "cursor-pointer",
        ].join(" "),
      },
    },
    defaultVariants: {
      variant: "standard",
    },
  },
);

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, ...props }, ref) => (
    <div ref={ref} className={cn(cardVariants({ variant, className }))} {...props} />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-1 p-5", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("type-subheading text-fg-primary", className)} {...props} />
  ),
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("type-body-tight text-fg-muted", className)} {...props} />
  ),
);
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-5 pt-0", className)} {...props} />
  ),
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-5 pt-0", className)} {...props} />
  ),
);
CardFooter.displayName = "CardFooter";

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter, cardVariants };
