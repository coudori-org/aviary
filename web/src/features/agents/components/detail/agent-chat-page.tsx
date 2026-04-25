"use client";

import * as React from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { ChatView } from "@/features/chat/components/chat-view";
import { ChatActionsProvider } from "@/features/chat/hooks/chat-actions-context";
import { useAgentDetail } from "@/features/agents/hooks/use-agent-detail";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { WorkspacePanel } from "@/features/workspace/components/workspace-panel";
import { SessionsRail } from "./sessions-rail";
import { EmptyChat } from "./empty-chat";
import { AgentCrumb } from "./agent-crumb";
import { AgentSubHeader } from "./agent-sub-header";

const WORKSPACE_OPEN_KEY = "aviary:workspace-panel-open";

/**
 * Agent home — the chat surface. Outer AppShell header carries the
 * breadcrumb (`Agents › agent name`) so the chat pane stays full-height;
 * no in-pane chat header.
 */
export function AgentChatPage({ agentId }: { agentId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sessionParam = searchParams.get("session");

  const detail = useAgentDetail(agentId);

  const crumb = React.useMemo(
    () => (detail.agent ? <AgentCrumb agent={detail.agent} /> : null),
    [detail.agent],
  );
  usePageCrumb(crumb);

  const setSession = React.useCallback(
    (sessionId: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (sessionId === null) params.delete("session");
      else params.set("session", sessionId);
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  // Auto-pick most recent session on entry.
  React.useEffect(() => {
    if (sessionParam) return;
    if (detail.loading) return;
    const first = detail.sessions[0];
    if (first) setSession(first.id);
  }, [sessionParam, detail.loading, detail.sessions, setSession]);

  // Drop stale ?session= when the active session is gone.
  React.useEffect(() => {
    if (!sessionParam || detail.loading) return;
    if (!detail.sessions.some((s) => s.id === sessionParam)) setSession(null);
  }, [sessionParam, detail.loading, detail.sessions, setSession]);

  const handleCreate = React.useCallback(async () => {
    const session = await detail.createSession();
    if (session) setSession(session.id);
  }, [detail, setSession]);

  // Workspace rail: persist open/close so the user's last choice sticks
  // across navigation. Default closed to match the "chat-first" entry.
  const [workspaceOpen, setWorkspaceOpen] = React.useState(false);
  React.useEffect(() => {
    try {
      setWorkspaceOpen(window.localStorage.getItem(WORKSPACE_OPEN_KEY) === "1");
    } catch {
      // Private mode / quota — keep default.
    }
  }, []);
  const toggleWorkspace = React.useCallback(() => {
    setWorkspaceOpen((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(WORKSPACE_OPEN_KEY, next ? "1" : "0");
      } catch {
        // Ignore storage failures — state still correct in memory.
      }
      return next;
    });
  }, []);

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

  // Only the chat surface owns the workspace toggle — the sub-header
  // hides the button entirely until a session is selected.
  const showWorkspace = workspaceOpen && Boolean(sessionParam);

  return (
    <ChatActionsProvider>
      <div className="flex h-full flex-col min-h-0">
        <AgentSubHeader
          agent={detail.agent}
          workspaceOpen={showWorkspace}
          onToggleWorkspace={sessionParam ? toggleWorkspace : undefined}
        />
        <div className="flex flex-1 min-h-0">
          <SessionsRail
            sessions={detail.sessions}
            selectedId={sessionParam}
            loading={detail.loading}
            creating={detail.creating}
            onSelect={(id) => setSession(id)}
            onCreate={handleCreate}
          />
          <div className="relative flex min-w-0 flex-1 flex-col">
            {detail.createError && (
              <div className="border-b border-status-error bg-status-error-soft px-4 py-2 text-[12px] text-status-error">
                Failed to create session: {detail.createError}
              </div>
            )}
            {sessionParam ? (
              <div className="flex-1 overflow-hidden">
                <ChatView sessionId={sessionParam} hideHeader hideWorkspace />
              </div>
            ) : (
              <EmptyChat
                onCreate={handleCreate}
                creating={detail.creating}
                hasSessions={detail.sessions.length > 0}
              />
            )}
          </div>
          {showWorkspace && sessionParam && (
            <WorkspacePanel sessionId={sessionParam} onClose={toggleWorkspace} />
          )}
        </div>
      </div>
    </ChatActionsProvider>
  );
}
