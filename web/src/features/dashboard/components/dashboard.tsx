"use client";

import Link from "next/link";
import { Plus } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { routes } from "@/lib/constants/routes";
import { useDashboardData } from "../hooks/use-dashboard-data";
import { StatCard } from "./stat-card";
import { RecentSessionsCard } from "./recent-sessions-card";
import { RecentRunsCard } from "./recent-runs-card";
import { PublishedReachCard } from "./published-reach-card";

export function Dashboard() {
  const { user } = useAuth();
  const data = useDashboardData();
  const greeting = `Hello, ${user?.display_name?.trim() || "there"}`;
  const today = formatToday();

  return (
    <div className="h-full overflow-y-auto px-8 pb-12 pt-6">
      <div className="mx-auto max-w-[1400px]">
        <header className="mb-5 flex items-baseline justify-between gap-4">
          <div>
            <h1 className="t-hero fg-primary">{greeting}</h1>
            <div className="mt-[2px] t-small fg-tertiary">{today}</div>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href={routes.workflowNew}>
                <Plus size={13} /> New Workflow
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link href={routes.agentNew}>
                <Plus size={13} /> New Agent
              </Link>
            </Button>
          </div>
        </header>

        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard
            label="Chat sessions"
            value={data.totalSessions}
            sub="Last 7 days"
            sparkline={{ data: data.sessionsByDay, color: "var(--accent-blue)" }}
          />
          <StatCard
            label="Workflow runs"
            value={data.totalRuns}
            sub="Last 7 days"
            sparkline={{ data: data.runsByDay, color: "var(--status-live)" }}
          />
          <StatCard
            label="Agents"
            value={data.agents.length}
            breakdown={[
              { label: "Published", value: data.publishedAgentsCount },
              { label: "Installs", value: data.agentInstallsCount },
            ]}
          />
          <StatCard
            label="Workflows"
            value={data.workflows.length}
            breakdown={[
              { label: "Published", value: data.publishedWorkflowsCount },
              { label: "Installs", value: data.workflowInstallsCount },
            ]}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.3fr_1fr]">
          <RecentSessionsCard sessions={data.recentSessions} loading={data.loading} />
          <PublishedReachCard />
        </div>

        <div className="mt-4">
          <RecentRunsCard runs={data.recentRuns} loading={data.loading} />
        </div>

        {data.error && (
          <div className="mt-4 rounded-[10px] border border-status-error bg-status-error-soft px-4 py-3 text-[12.5px] text-status-error">
            Failed to load dashboard data: {data.error}
          </div>
        )}
      </div>
    </div>
  );
}

function formatToday(): string {
  return new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}
