"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { Agent, Session } from "@/types";

interface SidebarAgent {
  agent: Agent;
  sessions: Session[];
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
                        <Link
                          href={`/agents/${agent.id}`}
                          className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                            isAgentActive(agent.id)
                              ? "text-foreground"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          <span className="text-sm">{agent.icon || "🤖"}</span>
                          <span className="truncate">{agent.name}</span>
                        </Link>

                        {/* Session list */}
                        <div className="ml-5 space-y-0.5 border-l border-border/30 pl-3">
                          {sessions.map((session) => (
                            <Link
                              key={session.id}
                              href={`/sessions/${session.id}`}
                              className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors ${
                                isSessionActive(session.id)
                                  ? "bg-primary/10 text-primary"
                                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                              }`}
                            >
                              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                              <span className="truncate">
                                {session.title || "Untitled"}
                              </span>
                            </Link>
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
                {user?.is_platform_admin && (
                  <span className="text-[9px] font-semibold uppercase tracking-wider text-primary">
                    Admin
                  </span>
                )}
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
  );
}
