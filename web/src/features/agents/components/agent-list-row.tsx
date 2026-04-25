"use client";

import Link from "next/link";
import { ChevronRight } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { KindBadge, type AssetKind } from "@/components/ui/kind-badge";
import { toneFromId, initialFromName } from "@/lib/tone";
import { formatRelativeTime, cn } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import type { Agent } from "@/types";

export const AGENT_LIST_COLS =
  "grid grid-cols-[2fr_2.2fr_110px_70px_80px_110px_28px] gap-3 items-center";

export interface AgentListRowProps {
  agent: Agent;
  sessionCount?: number;
  toolCount?: number;
  kind?: AssetKind;
  divider?: boolean;
}

export function AgentListRow({
  agent,
  sessionCount,
  toolCount,
  kind = "private",
  divider = true,
}: AgentListRowProps) {
  const tone = toneFromId(agent.id);
  const tools =
    toolCount ?? (agent.tools?.length ?? 0) + (agent.mcp_servers?.length ?? 0);
  return (
    <Link
      href={routes.agent(agent.id)}
      className={cn(
        AGENT_LIST_COLS,
        "px-4 py-[10px] transition-colors duration-fast hover:bg-hover",
        divider && "border-b border-border-subtle"
      )}
    >
      <div className="flex min-w-0 items-center gap-[10px]">
        <Avatar tone={tone} size="md">
          {agent.icon || initialFromName(agent.name)}
        </Avatar>
        <span className="truncate text-[13px] font-medium text-fg-primary">
          {agent.name}
        </span>
      </div>
      <span className="truncate text-[12px] text-fg-tertiary">
        {agent.description?.trim() || "—"}
      </span>
      <KindBadge kind={kind} />
      <span className="num t-mono text-fg-secondary">{tools}</span>
      <span className="num t-mono text-fg-secondary">{sessionCount ?? 0}</span>
      <span className="text-[11.5px] text-fg-muted">
        {formatRelativeTime(agent.updated_at)}
      </span>
      <ChevronRight size={14} className="text-fg-muted" />
    </Link>
  );
}
