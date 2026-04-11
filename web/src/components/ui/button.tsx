import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Button — Raycast-inspired variants.
 *
 * - primary:   pill, transparent, multi-layer inset shadow, hover via opacity
 * - cta:       pill, white background, dark text — for hero CTAs
 * - secondary: rectangular 6px, subtle border, opacity hover
 * - ghost:     no background, muted → primary on hover
 * - danger:    transparent with red glow border
 * - icon:      square 32px, 6px radius, hover background
 *
 * Following DESIGN.md, hover transitions use opacity rather than color swaps.
 */
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap select-none",
    "transition-[opacity,transform,background,border-color] duration-150",
    "disabled:pointer-events-none disabled:opacity-30",
    "focus-visible:outline-none",
    "active:scale-[0.98]",
  ].join(" "),
  {
    variants: {
      variant: {
        primary: [
          "type-button",
          "rounded-pill",
          "text-fg-primary",
          "shadow-3",
          "hover:opacity-60",
        ].join(" "),
        cta: [
          "type-button",
          "rounded-pill",
          "bg-white/[0.815] text-fg-on-light",
          "shadow-3",
          "hover:bg-white",
        ].join(" "),
        secondary: [
          "type-button",
          "rounded-sm border border-white/10",
          "text-fg-primary",
          "shadow-1",
          "hover:opacity-60",
        ].join(" "),
        ghost: [
          "type-button",
          "rounded-pill",
          "text-fg-muted",
          "hover:text-fg-primary hover:opacity-90",
        ].join(" "),
        danger: [
          "type-button",
          "rounded-sm border border-danger/30 bg-danger/10",
          "text-danger",
          "hover:bg-danger/20",
        ].join(" "),
        icon: [
          "rounded-sm",
          "text-fg-muted",
          "hover:bg-raised hover:text-fg-primary",
        ].join(" "),
      },
      size: {
        sm: "h-8 px-3 text-[12px]",
        md: "h-9 px-4",
        lg: "h-11 px-6",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    const finalSize = variant === "icon" && !size ? "icon" : size;
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size: finalSize, className }))}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
