"use client";

import Link from "next/link";
import { ChevronRight } from "@/components/icons";
import type { Agent } from "@/types";

export interface AgentCrumbProps {
  agent: Agent;
  /** Trailing segment after the agent name (e.g. "Detail", "Edit"). */
  trailing?: string;
}

/**
 * Minimal text-only breadcrumb for the AppShell header slot:
 *   Agents › Agent name [› trailing]
 */
export function AgentCrumb({ agent, trailing }: AgentCrumbProps) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex min-w-0 items-center gap-2 text-[12.5px]"
    >
      <Link href="/agents" className="text-fg-tertiary hover:text-fg-primary">
        Agents
      </Link>
      <ChevronRight size={11} className="text-fg-muted shrink-0" />
      <span className="truncate font-medium text-fg-primary">{agent.name}</span>
      {trailing && (
        <>
          <ChevronRight size={11} className="text-fg-muted shrink-0" />
          <span className="truncate text-fg-tertiary">{trailing}</span>
        </>
      )}
    </nav>
  );
}
