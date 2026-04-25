import Link from "next/link";
import { MessageSquare } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { toneFromId } from "@/lib/tone";
import { formatRelativeTime } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import type { DashboardSession } from "../hooks/use-dashboard-data";

export interface RecentSessionsCardProps {
  sessions: DashboardSession[];
  loading?: boolean;
}

export function RecentSessionsCard({ sessions, loading }: RecentSessionsCardProps) {
  return (
    <section
      className={cn(
        "flex flex-col rounded-[10px] border border-border-subtle bg-raised overflow-hidden"
      )}
    >
      <header className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <h2 className="t-h3 fg-primary">Recent chat sessions</h2>
        <Link
          href={routes.agents}
          className="text-[11.5px] font-medium text-accent hover:underline"
        >
          All agents →
        </Link>
      </header>
      <div className="flex flex-col">
        {loading && sessions.length === 0 ? (
          <SkeletonRows count={4} />
        ) : sessions.length === 0 ? (
          <EmptyState />
        ) : (
          sessions.map(({ session, agent }, i) => {
            const tone = toneFromId(agent.id);
            const title = session.title?.trim() || "(Untitled)";
            return (
              <Link
                key={session.id}
                href={routes.session(session.id)}
                className={cn(
                  "flex items-center gap-3 px-4 py-3 transition-colors duration-fast",
                  "hover:bg-hover",
                  i < sessions.length - 1 && "border-b border-border-subtle"
                )}
              >
                <Avatar tone={tone} size="md">
                  <MessageSquare size={14} />
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[13px] font-medium text-fg-primary">
                      {title}
                    </span>
                    <span className="text-[11px] text-fg-muted">·</span>
                    <span className="truncate text-[11.5px] text-fg-tertiary">
                      {agent.name}
                    </span>
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="text-[11px] text-fg-muted">
                    {formatRelativeTime(session.last_message_at ?? session.created_at)}
                  </div>
                </div>
              </Link>
            );
          })
        )}
      </div>
    </section>
  );
}

function EmptyState() {
  return (
    <div className="px-4 py-10 text-center text-[12.5px] text-fg-muted">
      No conversations yet. Start your first one with an agent.
    </div>
  );
}

function SkeletonRows({ count }: { count: number }) {
  return (
    <div className="flex flex-col">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "flex items-center gap-3 px-4 py-3",
            i < count - 1 && "border-b border-border-subtle"
          )}
        >
          <div className="h-[26px] w-[26px] shrink-0 animate-shimmer rounded-[6px]" />
          <div className="flex flex-1 flex-col gap-1">
            <div className="h-3 w-3/5 animate-shimmer rounded-[4px]" />
            <div className="h-2.5 w-2/5 animate-shimmer rounded-[4px]" />
          </div>
        </div>
      ))}
    </div>
  );
}
