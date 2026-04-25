"use client";

import Link from "next/link";
import {
  Bot,
  Check,
  Download,
  Plus,
  Star,
  Workflow as WorkflowIcon,
} from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { routes } from "@/lib/constants/routes";
import { toneFromId } from "@/lib/tone";
import { cn } from "@/lib/utils";
import type { MarketplaceItemSummary } from "@/types/marketplace";

export const MARKETPLACE_ROW_COLS =
  "grid items-center gap-4 grid-cols-[auto_1fr_140px_auto_120px]";

const N = new Intl.NumberFormat("en-US");

interface Props {
  item: MarketplaceItemSummary;
  divider?: boolean;
}

export function MarketplaceRow({ item, divider }: Props) {
  const tone = toneFromId(item.id);
  const Icon = item.kind === "workflow" ? WorkflowIcon : Bot;
  return (
    <Link
      href={routes.marketplaceItem(item.id)}
      className={cn(
        MARKETPLACE_ROW_COLS,
        "px-4 py-3 transition-colors duration-fast hover:bg-hover",
        divider && "border-b border-border-subtle",
      )}
    >
      <Avatar tone={tone} size="md">
        <Icon size={13} />
      </Avatar>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="t-body font-medium fg-primary truncate">{item.name}</span>
          <span className="t-mono text-[11px] text-fg-tertiary">{item.version}</span>
          {item.new_update && (
            <Badge variant="warning" className="h-[18px] text-[10px]">
              NEW
            </Badge>
          )}
        </div>
        <div className="mt-0.5 truncate text-[11.5px] text-fg-tertiary">
          {item.description}
        </div>
      </div>
      <div className="flex items-center gap-3 text-[11.5px] text-fg-tertiary tabular-nums">
        <span className="inline-flex items-center gap-1">
          <Star size={11} className="text-status-warn" />
          <span className="t-mono">{item.rating.toFixed(1)}</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <Download size={11} />
          <span className="t-mono">{N.format(item.installs)}</span>
        </span>
      </div>
      <Badge variant="default" className="h-[19px] text-[10.5px]">
        {item.category}
      </Badge>
      <div className="flex justify-end">
        {item.imported ? (
          <span className="inline-flex items-center gap-1 rounded-[4px] bg-status-live-soft px-2 py-[3px] text-[10.5px] font-semibold text-status-live">
            <Check size={10} strokeWidth={2.4} /> Imported
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-[4px] border border-border bg-transparent px-2 py-[3px] text-[10.5px] font-semibold text-fg-secondary group-hover:text-fg-primary">
            <Plus size={10} strokeWidth={2.4} /> Import
          </span>
        )}
      </div>
    </Link>
  );
}
