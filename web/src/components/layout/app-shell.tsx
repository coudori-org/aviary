"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";
import { useAgentStatus, useSetAgentIds } from "@/components/providers/agent-status-provider";
import { useSessionStatus, useSetSessionIds } from "@/components/providers/session-status-provider";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { Agent, Session } from "@/types";

interface SidebarAgent {
  agent: Agent;
  sessions: Session[];
}

interface SidebarContextValue {
  updateSessionTitle: (sessionId: string, title: string) => void;
  deleteSession: (sessionId: string) => Promise<void>;
}

const SidebarContext = createContext<SidebarContextValue>({
  updateSessionTitle: () => {},
  deleteSession: async () => {},
});

export function useSidebar() {
  return useContext(SidebarContext);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [sidebarData, setSidebarData] = useState<SidebarAgent[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);

  const refreshSidebar = useCallback(async () => {
    if (!user) return;
    try {
      const agentsRes = await apiFetch<{ items: Agent[] }>("/agents");
      const agents = agentsRes.items;

      const withSessions = await Promise.all(
        agents.map(async (agent) => {
          try {
            const sessionsRes = await apiFetch<{ items: Session[] }>(
              `/agents/${agent.id}/sessions`
            );
            return {
              agent,
              sessions: sessionsRes.items.filter((s) => s.status === "active"),
            };
          } catch {
            return { agent, sessions: [] };
          }
        })
      );

      setSidebarData(withSessions);
    } catch {
      // Silently fail — sidebar is non-blocking
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refreshSidebar();
  }, [refreshSidebar]);

  // Refresh sidebar when navigating to a new session (session may have been just created)
  useEffect(() => {
    if (pathname.startsWith("/sessions/")) {
      refreshSidebar();
    }
  }, [pathname, refreshSidebar]);

  // Feed session IDs to the status provider for polling
  const setSessionIds = useSetSessionIds();
  useEffect(() => {
    const allSessionIds = sidebarData
      .flatMap((d) => d.sessions)
      .map((s) => s.id);
    setSessionIds(allSessionIds);
  }, [sidebarData, setSessionIds]);

  // Feed agent IDs to the agent status provider for polling
  const setAgentIds = useSetAgentIds();
  useEffect(() => {
    const allAgentIds = sidebarData
      .filter((d) => d.sessions.length > 0)
      .map((d) => d.agent.id);
    setAgentIds(allAgentIds);
  }, [sidebarData, setAgentIds]);

  const updateSessionTitle = useCallback((sessionId: string, title: string) => {
    setSidebarData((prev) =>
      prev.map((d) => ({
        ...d,
        sessions: d.sessions.map((s) =>
          s.id === sessionId ? { ...s, title } : s
        ),
      }))
    );
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    await apiFetch(`/sessions/${sessionId}`, { method: "DELETE" });
    setSidebarData((prev) =>
      prev.map((d) => ({
        ...d,
        sessions: d.sessions.filter((s) => s.id !== sessionId),
      }))
    );
  }, []);

  const isActive = (href: string) => pathname === href;
  const isSessionActive = (sessionId: string) =>
    pathname === `/sessions/${sessionId}`;
  const isAgentActive = (agentId: string) =>
    pathname.startsWith(`/agents/${agentId}`);

  const totalSessions = sidebarData.reduce(
    (sum, d) => sum + d.sessions.length,
    0
  );

  return (
    <SidebarContext.Provider value={{ updateSessionTitle, deleteSession }}>
      <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`flex shrink-0 flex-col border-r border-border/40 bg-card transition-all duration-200 ${
          collapsed ? "w-16" : "w-64"
        }`}
      >
        {/* Logo */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border/40 px-4">
          {!collapsed && (
            <Link href="/agents" className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-primary"
                >
                  <path d="M12 2L2 7l10 5 10-5-10-5z" />
                  <path d="M2 17l10 5 10-5" />
                  <path d="M2 12l10 5 10-5" />
                </svg>
              </div>
              <span className="text-sm font-semibold text-foreground">
                Aviary
              </span>
            </Link>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {collapsed ? (
                <>
                  <polyline points="9 18 15 12 9 6" />
                </>
              ) : (
                <>
                  <polyline points="15 18 9 12 15 6" />
                </>
              )}
            </svg>
          </button>
        </div>

        {/* Nav items */}
        <div className="flex-1 overflow-y-auto py-3">
          {/* Main nav */}
          <div className="px-3 pb-2">
            <Link
              href="/agents"
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive("/agents")
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
              }`}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </svg>
              {!collapsed && "All Agents"}
            </Link>
          </div>

          {/* Sessions grouped by agent */}
          {!collapsed && (
            <div className="px-3 pt-2">
              <div className="mb-2 flex items-center justify-between px-3">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                  Active Sessions
                  {totalSessions > 0 && (
                    <span className="ml-1.5 rounded-full bg-primary/10 px-1.5 py-0 text-[9px] text-primary">
                      {totalSessions}
                    </span>
                  )}
                </span>
              </div>

              {loading ? (
                <div className="space-y-2 px-3">
                  {[...Array(3)].map((_, i) => (
                    <div
                      key={i}
                      className="h-6 animate-shimmer rounded"
                    />
                  ))}
                </div>
              ) : sidebarData.filter((d) => d.sessions.length > 0).length ===
                0 ? (
                <p className="px-3 text-xs text-muted-foreground/50">
                  No active sessions
                </p>
              ) : (
                <div className="space-y-1">
                  {sidebarData
                    .filter((d) => d.sessions.length > 0)
                    .map(({ agent, sessions }) => (
                      <div key={agent.id}>
                        {/* Agent group header */}
                        <SidebarAgentHeader
                          agent={agent}
                          isActive={isAgentActive(agent.id)}
                        />

                        {/* Session list */}
                        <div className="ml-5 space-y-0.5 border-l border-border/30 pl-3">
                          {sessions.map((session) => (
                            <SidebarSessionItem
                              key={session.id}
                              session={session}
                              isActive={isSessionActive(session.id)}
                            />
                          ))}
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* User section */}
        <div className="shrink-0 border-t border-border/40 p-3">
          {collapsed ? (
            <button
              onClick={logout}
              className="flex h-8 w-full items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
              title="Sign out"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          ) : (
            <div className="flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-foreground/80">
                  {user?.display_name || user?.email}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={logout}
                className="h-7 text-xs text-muted-foreground"
              >
                Sign out
              </Button>
            </div>
          )}
        </div>
      </aside>

        {/* Main content */}
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </SidebarContext.Provider>
  );
}

function SidebarAgentHeader({
  agent,
  isActive,
}: {
  agent: Agent;
  isActive: boolean;
}) {
  const readiness = useAgentStatus(agent.id);
  const isDeleted = agent.status === "deleted";

  return (
    <Link
      href={`/agents/${agent.id}`}
      className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
        isActive
          ? "text-foreground"
          : "text-muted-foreground hover:text-foreground"
      }`}
    >
      <span className={`text-sm ${isDeleted ? "grayscale opacity-40" : ""}`}>{agent.icon || "🤖"}</span>
      <span className={`truncate flex-1 ${isDeleted ? "text-muted-foreground/50 line-through decoration-muted-foreground/70 decoration-1" : ""}`}>
        {agent.name}
      </span>
      {isDeleted ? (
        <span className="shrink-0 text-[9px] text-destructive/50">deleted</span>
      ) : (
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
            readiness === "ready" ? "bg-success" : "bg-muted-foreground/50"
          }`}
          title={readiness === "ready" ? "Agent ready" : "Agent offline"}
        />
      )}
    </Link>
  );
}

function SidebarSessionItem({
  session,
  isActive,
}: {
  session: Session;
  isActive: boolean;
}) {
  const { status, unread, title: polledTitle } = useSessionStatus(session.id);
  const { deleteSession } = useSidebar();
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setDeleting(true);
    try {
      await deleteSession(session.id);
      if (isActive) router.push("/agents");
    } catch {
      setDeleting(false);
      setConfirming(false);
    }
  };

  return (
    <Link
      href={`/sessions/${session.id}`}
      className={`group flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs transition-colors ${
        isActive
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
      } ${deleting ? "opacity-50 pointer-events-none" : ""}`}
      onMouseLeave={() => setConfirming(false)}
    >
      {confirming ? (
        <span className="truncate flex-1 text-destructive">Delete?</span>
      ) : (
        <span className="truncate flex-1">
          {polledTitle || session.title || "Untitled"}
        </span>
      )}
      {status === "streaming" && !confirming && (
        <svg
          className="h-3.5 w-3.5 shrink-0 animate-spin text-primary"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="3"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      )}
      {unread > 0 && !isActive && status !== "streaming" && !confirming && (
        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[9px] font-semibold text-primary-foreground">
          {unread > 99 ? "99+" : unread}
        </span>
      )}
      <button
        onClick={handleDelete}
        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded transition-colors ${
          confirming
            ? "text-destructive hover:text-destructive"
            : "opacity-0 group-hover:opacity-100 text-muted-foreground/50 hover:text-destructive"
        }`}
        title={confirming ? "Click to confirm" : "Delete session"}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {confirming ? (
            <>
              <polyline points="20 6 9 17 4 12" />
            </>
          ) : (
            <>
              <path d="M3 6h18" />
              <path d="M8 6V4h8v2" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
            </>
          )}
        </svg>
      </button>
    </Link>
  );
}
