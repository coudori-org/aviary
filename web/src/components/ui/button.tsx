import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const newVariants = {
  default:
    "bg-accent text-white border border-accent hover:bg-accent/90 hover:border-accent/90",
  outline:
    "bg-raised border border-border text-fg-primary hover:bg-hover hover:border-border-strong",
  ghost:
    "border border-transparent text-fg-secondary hover:bg-hover hover:text-fg-primary",
  destructive:
    "bg-destructive text-destructive-foreground border border-destructive hover:brightness-110",
  link:
    "border border-transparent text-accent underline-offset-4 hover:underline",
} as const;

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-1.5 whitespace-nowrap select-none",
    "rounded-[7px] text-[12.5px] font-medium",
    "transition-[background,border-color,color] duration-fast",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-soft focus-visible:ring-offset-0",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        ...newVariants,
        // ── legacy aliases (mapped to closest Slate look) ──
        primary: newVariants.default,
        cta: newVariants.default,
        secondary: newVariants.outline,
        danger: newVariants.destructive,
        icon: newVariants.ghost,
      },
      size: {
        default: "h-[30px] px-3",
        sm: "h-[26px] px-[9px] text-[12px] rounded-[6px]",
        lg: "h-[34px] px-4 text-[13.5px]",
        icon: "h-[30px] w-[30px] p-0",
        // legacy alias
        md: "h-[30px] px-3",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    const finalSize = variant === "icon" && !size ? "icon" : size;
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size: finalSize, className }))}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
