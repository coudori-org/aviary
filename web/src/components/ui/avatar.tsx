import * as React from "react";
import { cn } from "@/lib/utils";

export type Tone = "blue" | "green" | "amber" | "pink" | "purple" | "teal" | "rose" | "slate";
type Size = "sm" | "md" | "lg" | "xl";
type Shape = "square" | "circle";

const sizeMap: Record<Size, { box: string; text: string; radius: string }> = {
  sm: { box: "w-[20px] h-[20px]", text: "text-[9px]",  radius: "rounded-[5px]" },
  md: { box: "w-[26px] h-[26px]", text: "text-[11px]", radius: "rounded-[6px]" },
  lg: { box: "w-[36px] h-[36px]", text: "text-[13px]", radius: "rounded-[8px]" },
  xl: { box: "w-[52px] h-[52px]", text: "text-[18px]", radius: "rounded-[11px]" },
};

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  tone: Tone;
  size?: Size;
  shape?: Shape;
}

export const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(
  ({ tone, size = "lg", shape = "square", className, children, ...props }, ref) => {
    const s = sizeMap[size];
    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center font-semibold shrink-0",
          `tone-${tone}`,
          s.box,
          s.text,
          shape === "circle" ? "rounded-full" : s.radius,
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);
Avatar.displayName = "Avatar";
