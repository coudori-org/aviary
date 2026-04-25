"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Pencil, MessageSquare, Wrench, Brain, Clock } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { AgentCrumb } from "@/features/agents/components/detail/agent-crumb";
import { ToolChip } from "@/features/agents/components/form/tool-chip";
import { ToolDetailsSheet } from "@/features/agents/components/tool-selector/tool-details-sheet";
import { useAgentDetail } from "@/features/agents/hooks/use-agent-detail";
import { agentsApi } from "@/features/agents/api/agents-api";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { toneFromId, initialFromName } from "@/lib/tone";
import { formatRelativeTime, formatTokens, cn } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import type { McpToolInfo } from "@/types";

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const detail = useAgentDetail(params.id);
  const [tools, setTools] = React.useState<McpToolInfo[]>([]);
  const [detailsTool, setDetailsTool] = React.useState<McpToolInfo | null>(null);

  React.useEffect(() => {
    let alive = true;
    agentsApi
      .getMcpTools(params.id)
      .then((bindings) => {
        if (alive) setTools(bindings.map((b) => b.tool));
      })
      .catch(() => {
        if (alive) setTools([]);
      });
    return () => {
      alive = false;
    };
  }, [params.id]);

  const crumb = React.useMemo(
    () => (detail.agent ? <AgentCrumb agent={detail.agent} trailing="Detail" /> : null),
    [detail.agent],
  );
  usePageCrumb(crumb);

  const toolMap = React.useMemo(() => {
    const m = new Map<string, McpToolInfo>();
    for (const t of tools) m.set(t.id, t);
    return m;
  }, [tools]);

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
  const lastActive = detail.sessions.reduce<string | null>((latest, s) => {
    const ts = s.last_message_at ?? s.created_at;
    return !latest || ts > latest ? ts : latest;
  }, null);

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
                <span>{agent.slug}</span>
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

        <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatTile
            icon={<MessageSquare size={14} />}
            label="Sessions"
            value={detail.sessions.length}
          />
          <StatTile
            icon={<Wrench size={14} />}
            label="Tools"
            value={(agent.tools?.length ?? 0) + tools.length}
          />
          <StatTile
            icon={<Brain size={14} />}
            label="Model"
            value={agent.model_config?.model ?? agent.model_config?.backend ?? "—"}
            mono
          />
          <StatTile
            icon={<Clock size={14} />}
            label="Last activity"
            value={lastActive ? formatRelativeTime(lastActive) : "Never"}
          />
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
          <Section title="System instruction">
            {agent.instruction ? (
              <pre
                className={cn(
                  "whitespace-pre-wrap break-words rounded-[7px] bg-sunk p-3",
                  "t-mono text-[12px] text-fg-secondary border border-border-subtle"
                )}
              >
                {agent.instruction}
              </pre>
            ) : (
              <EmptyLine>No instruction set.</EmptyLine>
            )}
          </Section>

          <Section title="Recent sessions">
            {detail.sessions.length === 0 ? (
              <EmptyLine>No sessions yet.</EmptyLine>
            ) : (
              <ul className="flex flex-col">
                {detail.sessions.slice(0, 5).map((s, i, arr) => (
                  <li key={s.id}>
                    <Link
                      href={routes.agentChat(agent.id, s.id)}
                      className={cn(
                        "flex items-center justify-between gap-3 px-3 py-[10px]",
                        "transition-colors duration-fast hover:bg-hover",
                        i < arr.length - 1 && "border-b border-border-subtle"
                      )}
                    >
                      <span className="truncate text-[12.5px] text-fg-primary">
                        {s.title?.trim() || "(Untitled)"}
                      </span>
                      <span className="shrink-0 text-[11px] text-fg-muted">
                        {formatRelativeTime(s.last_message_at ?? s.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <Section title="Model configuration">
            <KvRow k="Backend" v={agent.model_config?.backend ?? "—"} />
            <KvRow k="Model" v={agent.model_config?.model ?? "—"} mono />
            <KvRow
              k="Max output tokens"
              v={
                agent.model_config?.max_output_tokens != null
                  ? formatTokens(agent.model_config.max_output_tokens)
                  : "—"
              }
              mono
            />
          </Section>

          <Section title="Skills">
            {agent.tools && agent.tools.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {agent.tools.map((t) => (
                  <Badge key={t} variant="default" className="t-mono">
                    {t}
                  </Badge>
                ))}
              </div>
            ) : (
              <EmptyLine>No skills yet.</EmptyLine>
            )}
          </Section>
        </div>

        <Section title="MCP tools" className="mt-6">
          {tools.length === 0 ? (
            <EmptyLine>No MCP tools bound.</EmptyLine>
          ) : (
            <div className="flex flex-wrap gap-2">
              {tools.map((t) => (
                <ToolChip
                  key={t.id}
                  id={t.id}
                  info={toolMap.get(t.id)}
                  onRemove={() => undefined}
                  onShowDetails={setDetailsTool}
                />
              ))}
            </div>
          )}
        </Section>
      </div>
      <ToolDetailsSheet tool={detailsTool} onClose={() => setDetailsTool(null)} />
    </div>
  );
}

function StatTile({
  icon,
  label,
  value,
  mono,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-[10px] border border-border-subtle bg-raised p-3">
      <div className="flex items-center gap-1.5 t-small fg-tertiary">
        {icon}
        <span>{label}</span>
      </div>
      <div
        className={cn(
          "num mt-1 truncate text-[18px] font-semibold leading-tight text-fg-primary",
          mono && "t-mono text-[14px] font-medium"
        )}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </div>
    </div>
  );
}

function Section({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[10px] border border-border-subtle bg-raised",
        className
      )}
    >
      <header className="border-b border-border-subtle px-3 py-2">
        <h2 className="t-over fg-muted">{title}</h2>
      </header>
      <div className="px-3 py-3">{children}</div>
    </section>
  );
}

function KvRow({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 first:pt-0 last:pb-0">
      <span className="t-small fg-muted">{k}</span>
      <span
        className={cn(
          "truncate text-[12.5px] text-fg-primary",
          mono && "t-mono text-[12px]"
        )}
      >
        {v}
      </span>
    </div>
  );
}

function EmptyLine({ children }: { children: React.ReactNode }) {
  return <div className="t-small fg-muted">{children}</div>;
}
