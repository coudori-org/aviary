import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Button — Aurora Glass.
 *
 * - primary:   aurora-A gradient fill with violet glow + continuous sheen
 * - cta:       same as primary — louder drop shadow
 * - secondary: translucent glass pane, hairline border
 * - ghost:     no fill, muted → primary on hover
 * - danger:    pink-tinted glass with danger glow
 * - icon:      square glass tile
 *
 * Hover states lift (-1px translateY) + amplify glow. All transitions use
 * 320ms cubic-bezier(0.16, 1, 0.3, 1) — generous but not slow.
 */
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap select-none",
    "transition-all duration-[320ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
    "disabled:pointer-events-none disabled:opacity-40",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aurora-violet/50 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas",
    "active:translate-y-0 active:scale-[0.98]",
  ].join(" "),
  {
    variants: {
      variant: {
        primary: [
          "type-button rounded-pill",
          "bg-aurora-a animate-aurora-sheen",
          "text-white",
          "shadow-[0_0_32px_rgba(123,92,255,0.35),inset_0_1px_0_rgba(255,255,255,0.2)]",
          "hover:-translate-y-[1px] hover:shadow-[0_0_44px_rgba(123,92,255,0.5),inset_0_1px_0_rgba(255,255,255,0.25)]",
        ].join(" "),
        cta: [
          "type-button rounded-pill",
          "bg-aurora-a animate-aurora-sheen",
          "text-white",
          "shadow-[0_8px_28px_rgba(123,92,255,0.45),inset_0_1px_0_rgba(255,255,255,0.2)]",
          "hover:-translate-y-[1px] hover:shadow-[0_12px_40px_rgba(123,92,255,0.6),inset_0_1px_0_rgba(255,255,255,0.25)]",
        ].join(" "),
        secondary: [
          "type-button rounded-pill",
          "glass-raised text-fg-primary",
          "hover:-translate-y-[1px] hover:bg-white/[0.11]",
        ].join(" "),
        ghost: [
          "type-button rounded-pill",
          "text-fg-muted",
          "hover:text-fg-primary hover:bg-white/[0.05]",
        ].join(" "),
        danger: [
          "type-button rounded-pill",
          "bg-aurora-pink/15 border border-aurora-pink/30 text-aurora-pink",
          "hover:bg-aurora-pink/25 hover:shadow-[0_0_20px_rgba(255,79,184,0.35)]",
        ].join(" "),
        icon: [
          "rounded-sm",
          "text-fg-muted",
          "hover:bg-white/[0.07] hover:text-fg-primary",
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
