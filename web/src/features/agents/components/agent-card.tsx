"use client";

import Link from "next/link";
import { MessageSquare, Wrench } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { KindBadge, type AssetKind } from "@/components/ui/kind-badge";
import { toneFromId, initialFromName } from "@/lib/tone";
import { formatRelativeTime, cn } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import type { Agent } from "@/types";

export interface AgentCardProps {
  agent: Agent;
  /** Async-loaded counts (undefined = not loaded yet). */
  sessionCount?: number;
  toolCount?: number;
  /** Ownership state. Backend has no published/imported yet — defaults to private. */
  kind?: AssetKind;
}

export function AgentCard({
  agent,
  sessionCount,
  toolCount,
  kind = "private",
}: AgentCardProps) {
  const tone = toneFromId(agent.id);
  const tools = toolCount ?? (agent.tools?.length ?? 0) + (agent.mcp_servers?.length ?? 0);
  return (
    <Link
      href={routes.agent(agent.id)}
      className={cn(
        "group flex flex-col gap-[10px] p-[14px] text-left",
        "rounded-[10px] border border-border-subtle bg-raised",
        "transition-[background,border-color,transform,box-shadow] duration-fast",
        "hover:bg-hover hover:border-border hover:-translate-y-px hover:shadow-md"
      )}
    >
      <header className="flex items-start gap-[10px]">
        <Avatar tone={tone} size="lg">
          {agent.icon || initialFromName(agent.name)}
        </Avatar>
        <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <div className="flex items-center gap-[6px]">
            <span className="t-h3 fg-primary truncate tracking-[-0.005em]">
              {agent.name}
            </span>
          </div>
          <div className="flex items-center gap-[6px] text-[11.5px] text-fg-tertiary">
            <KindBadge kind={kind} />
            <span className="t-mono truncate text-[11px]">
              {agent.model_config?.model ?? agent.model_config?.backend ?? ""}
            </span>
          </div>
        </div>
      </header>

      <p
        className={cn(
          "text-[12.5px] leading-[1.45] text-fg-secondary",
          "min-h-[36px] line-clamp-2"
        )}
      >
        {agent.description?.trim() || "No description"}
      </p>

      <div className="my-[2px] h-px bg-border-subtle" />

      <footer className="flex items-center gap-3 text-[11.5px] text-fg-tertiary">
        <span className="inline-flex items-center gap-1">
          <Wrench size={12} />
          <span className="num t-mono">{tools}</span>
          <span className="text-fg-muted">tools</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <MessageSquare size={12} />
          <span className="num t-mono">{sessionCount ?? 0}</span>
          <span className="text-fg-muted">sessions</span>
        </span>
        <span className="flex-1" />
        <span className="text-[11px] text-fg-muted">
          {formatRelativeTime(agent.updated_at)}
        </span>
      </footer>
    </Link>
  );
}
