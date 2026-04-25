"use client";

import { useEffect, useState } from "react";
import { http } from "@/lib/http";
import type { Agent, Session, Workflow, WorkflowRun } from "@/types";

export interface DashboardSession {
  session: Session;
  agent: Agent;
}

export interface DashboardRun {
  run: WorkflowRun;
  workflow: Workflow;
}

export interface DashboardData {
  agents: Agent[];
  workflows: Workflow[];
  totalSessions: number;
  totalRuns: number;
  /** Newest-last bucket of session activity over the trailing 7 days. */
  sessionsByDay: number[];
  /** Newest-last bucket of workflow run activity over the trailing 7 days. */
  runsByDay: number[];
  /** Count of agents the user has published to the marketplace. */
  publishedAgentsCount: number;
  /** Count of workflows the user has published to the marketplace. */
  publishedWorkflowsCount: number;
  /** Total installs of this user's published agents by other users. */
  agentInstallsCount: number;
  /** Total installs of this user's published workflows by other users. */
  workflowInstallsCount: number;
  recentSessions: DashboardSession[];
  recentRuns: DashboardRun[];
  loading: boolean;
  error: string | null;
}

const RECENT_SESSIONS = 6;
const RECENT_RUNS = 8;
const RUNS_PER_WORKFLOW = 100;
const TREND_DAYS = 7;

export function useDashboardData(): DashboardData {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [totalSessions, setTotalSessions] = useState(0);
  const [totalRuns, setTotalRuns] = useState(0);
  const [sessionsByDay, setSessionsByDay] = useState<number[]>(() => zeros(TREND_DAYS));
  const [runsByDay, setRunsByDay] = useState<number[]>(() => zeros(TREND_DAYS));
  const [recentSessions, setRecentSessions] = useState<DashboardSession[]>([]);
  const [recentRuns, setRecentRuns] = useState<DashboardRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [agentRes, wfRes] = await Promise.all([
          http.get<{ items: Agent[] }>("/agents"),
          http.get<{ items: Workflow[] }>("/workflows"),
        ]);
        if (!alive) return;
        setAgents(agentRes.items);
        setWorkflows(wfRes.items);

        const sessionsByAgent = await Promise.all(
          agentRes.items.map((a) =>
            http
              .get<{ items: Session[] }>(`/agents/${a.id}/sessions`)
              .then((r) => ({ a, items: r.items }))
              .catch(() => ({ a, items: [] as Session[] })),
          ),
        );
        if (!alive) return;
        const allSessions = sessionsByAgent.flatMap(({ a, items }) =>
          items.map<DashboardSession>((s) => ({ session: s, agent: a })),
        );
        allSessions.sort((x, y) =>
          sortKey(y.session).localeCompare(sortKey(x.session)),
        );
        setTotalSessions(allSessions.length);
        setRecentSessions(allSessions.slice(0, RECENT_SESSIONS));
        setSessionsByDay(
          bucketByDay(allSessions, TREND_DAYS, (x) => sortKey(x.session)),
        );

        const runsByWf = await Promise.all(
          wfRes.items.map((w) =>
            http
              .get<{ items: WorkflowRun[]; total: number }>(
                `/workflows/${w.id}/runs?limit=${RUNS_PER_WORKFLOW}`,
              )
              .then((r) => ({ w, runs: r.items, total: r.total }))
              .catch(() => ({ w, runs: [] as WorkflowRun[], total: 0 })),
          ),
        );
        if (!alive) return;
        const allRuns = runsByWf.flatMap(({ w, runs }) =>
          runs.map<DashboardRun>((r) => ({ run: r, workflow: w })),
        );
        allRuns.sort((x, y) =>
          runSortKey(y.run).localeCompare(runSortKey(x.run)),
        );
        setTotalRuns(runsByWf.reduce((sum, r) => sum + r.total, 0));
        setRecentRuns(allRuns.slice(0, RECENT_RUNS));
        setRunsByDay(bucketByDay(allRuns, TREND_DAYS, (x) => runSortKey(x.run)));
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // TODO(marketplace): wire to real endpoints once Marketplace ships.
  // The shape is locked so swapping the source is a one-liner.
  const publishedAgentsCount = 0;
  const publishedWorkflowsCount = 0;
  const agentInstallsCount = 0;
  const workflowInstallsCount = 0;

  return {
    agents,
    workflows,
    totalSessions,
    totalRuns,
    sessionsByDay,
    runsByDay,
    publishedAgentsCount,
    publishedWorkflowsCount,
    agentInstallsCount,
    workflowInstallsCount,
    recentSessions,
    recentRuns,
    loading,
    error,
  };
}

function sortKey(s: Session): string {
  return s.last_message_at ?? s.created_at;
}

function runSortKey(r: WorkflowRun): string {
  return r.started_at ?? r.created_at;
}

function zeros(n: number): number[] {
  return Array(n).fill(0);
}

/**
 * Bucket items into `days` daily counts, oldest-first → newest-last.
 * Items outside the window are dropped. Index `days - 1` is today.
 */
function bucketByDay<T>(
  items: T[],
  days: number,
  getTs: (x: T) => string | undefined,
): number[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = today.getTime();
  const buckets = zeros(days);
  for (const x of items) {
    const ts = getTs(x);
    if (!ts) continue;
    const d = new Date(ts);
    if (isNaN(d.getTime())) continue;
    d.setHours(0, 0, 0, 0);
    const dayDiff = Math.round((start - d.getTime()) / 86400000);
    if (dayDiff >= 0 && dayDiff < days) {
      buckets[days - 1 - dayDiff]++;
    }
  }
  return buckets;
}
