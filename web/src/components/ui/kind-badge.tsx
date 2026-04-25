import * as React from "react";
import { Lock, Globe, Download } from "lucide-react";
import { cn } from "@/lib/utils";

export type AssetKind = "private" | "published" | "imported";

const config = {
  private:   { label: "Private",   cls: "bg-[var(--badge-private-bg)] text-[var(--badge-private-fg)]",     Icon: Lock },
  published: { label: "Published", cls: "bg-[var(--badge-published-bg)] text-[var(--badge-published-fg)]", Icon: Globe },
  imported:  { label: "Imported",  cls: "bg-[var(--badge-imported-bg)] text-[var(--badge-imported-fg)]",   Icon: Download },
} as const;

export interface KindBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  kind: AssetKind;
}

export function KindBadge({ kind, className, ...props }: KindBadgeProps) {
  const { label, cls, Icon } = config[kind];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 h-[19px] pl-[6px] pr-[7px] rounded-[4px]",
        "text-[10.5px] font-semibold tracking-[0.02em]",
        cls,
        className
      )}
      {...props}
    >
      <Icon size={10} strokeWidth={2.2} />
      {label}
    </span>
  );
}
