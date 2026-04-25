"use client";

import Link from "next/link";
import { Bot, Check, Download, Star, Workflow as WorkflowIcon } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { routes } from "@/lib/constants/routes";
import { toneFromId } from "@/lib/tone";
import { cn } from "@/lib/utils";
import type { MarketplaceItemSummary } from "@/types/marketplace";

const N = new Intl.NumberFormat("en-US");

interface Props {
  item: MarketplaceItemSummary;
  /** When true, paint the accent-tinted hero background. */
  featured?: boolean;
}

export function MarketplaceCard({ item, featured }: Props) {
  const tone = toneFromId(item.id);
  const Icon = item.kind === "workflow" ? WorkflowIcon : Bot;
  return (
    <Link
      href={routes.marketplaceItem(item.id)}
      className={cn(
        "group flex flex-col gap-3 rounded-[10px] border border-border-subtle bg-raised p-4",
        "transition-colors duration-fast hover:bg-hover",
        featured && "bg-gradient-to-br from-accent-soft via-raised to-raised",
      )}
    >
      <div className="flex items-start gap-3">
        <Avatar tone={tone} size="lg">
          <Icon size={16} />
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="t-h3 fg-primary truncate">{item.name}</span>
            {item.new_update && (
              <Badge variant="warning" className="h-[18px] text-[10px]">
                NEW
              </Badge>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-[11.5px] text-fg-tertiary">
            <span className="t-mono">{item.version}</span>
            <span>·</span>
            <span>{item.category}</span>
          </div>
        </div>
        {item.imported && (
          <span className="inline-flex items-center gap-1 rounded-[4px] bg-status-live-soft px-1.5 text-[10.5px] font-semibold text-status-live">
            <Check size={10} strokeWidth={2.4} /> Imported
          </span>
        )}
      </div>
      <p className="line-clamp-2 text-[12.5px] text-fg-secondary">
        {item.description}
      </p>
      <div className="mt-auto flex items-center gap-3 text-[11.5px] text-fg-tertiary tabular-nums">
        <span className="inline-flex items-center gap-1">
          <Star size={11} className="text-status-warn" />
          <span className="t-mono">{item.rating.toFixed(1)}</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <Download size={11} />
          <span className="t-mono">{N.format(item.installs)}</span>
        </span>
        <span className="ml-auto text-accent opacity-0 transition-opacity duration-fast group-hover:opacity-100">
          View →
        </span>
      </div>
    </Link>
  );
}
