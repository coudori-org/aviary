"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Pencil, Sparkles } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { AgentCrumb } from "@/features/agents/components/detail/agent-crumb";
import { useAgentDetail } from "@/features/agents/hooks/use-agent-detail";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { toneFromId, initialFromName } from "@/lib/tone";
import { routes } from "@/lib/constants/routes";

/**
 * Agent detail (read-only). Carries an Edit CTA that bounces to the
 * full edit page. Bulk of the layout lands in Stage B5/B6 (live preview,
 * full config grid). Today: identity card + Edit shortcut.
 */
export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const detail = useAgentDetail(params.id);

  const crumb = React.useMemo(
    () => (detail.agent ? <AgentCrumb agent={detail.agent} trailing="Detail" /> : null),
    [detail.agent],
  );
  usePageCrumb(crumb);

  if (detail.loading && !detail.agent) {
    return <LoadingState fullHeight label="Loading agent…" />;
  }
  if (detail.error || !detail.agent) {
    return (
      <ErrorState
        title="Couldn't load agent"
        description={detail.error ?? "Agent not found."}
      />
    );
  }

  const agent = detail.agent;
  const tone = toneFromId(agent.id);

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mx-auto max-w-[960px]">
        <header className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <Avatar tone={tone} size="xl">
              {agent.icon || initialFromName(agent.name)}
            </Avatar>
            <div className="min-w-0">
              <h1 className="t-h1 fg-primary truncate">{agent.name}</h1>
              <p className="mt-1 text-[13px] text-fg-secondary">
                {agent.description?.trim() || "No description"}
              </p>
              <div className="mt-2 inline-flex items-center gap-1 t-mono text-[11px] text-fg-tertiary">
                <span>{agent.model_config?.model ?? agent.model_config?.backend ?? "—"}</span>
                <span>·</span>
                <span>{agent.tools?.length ?? 0} tools</span>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href={routes.agentChat(agent.id)}>Open chat</Link>
            </Button>
            <Button asChild size="sm">
              <Link href={routes.agentEdit(agent.id)}>
                <Pencil size={13} /> Edit
              </Link>
            </Button>
          </div>
        </header>

        <div className="mt-8 flex flex-col items-center justify-center gap-3 rounded-[10px] border border-border-subtle bg-raised px-6 py-12 text-center">
          <div className="grid h-10 w-10 place-items-center rounded-[8px] bg-hover text-fg-tertiary">
            <Sparkles size={18} />
          </div>
          <div>
            <h2 className="t-h2 fg-primary">Detail view coming together</h2>
            <p className="mt-1 max-w-[420px] text-[12.5px] text-fg-muted">
              Full identity, instructions, tools, and stats land in Stage B5 / B6.
              Until then, jump into edit to change anything.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

