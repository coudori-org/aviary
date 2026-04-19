"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useChatMessages } from "@/features/chat/hooks/use-chat-messages";
import { useConnectionStatus } from "@/features/chat/hooks/use-connection-status";
import { useTitleEditor } from "@/features/chat/hooks/use-title-editor";
import { useChatExport } from "@/features/chat/hooks/use-chat-export";
import { ChatWidthProvider, useChatWidth } from "@/features/chat/hooks/use-chat-width";
import { useChatSearch } from "@/features/chat/hooks/use-chat-search";
import { ChatSearchContextProvider } from "@/features/chat/hooks/chat-search-context";
import { useAgentCapabilities } from "@/features/chat/hooks/use-agent-capabilities";
import { ChatHeader } from "./chat-header";
import { ChatStatusBanner } from "./chat-status-banner";
import { ChatSearchBar } from "./chat-search-bar";
import { MessageList } from "./message-list/message-list";
import { ChatInput } from "./input/chat-input";
import type { FileRef } from "@/types";
import { TodoPanel } from "./todos/todo-panel";
import { LoadingState } from "@/components/feedback/loading-state";
import { routes } from "@/lib/constants/routes";
import { WorkspacePanel } from "@/features/workspace/components/workspace-panel";

// Tools that modify the session's workspace — trigger an auto-refresh of the
// file-tree panel after they complete. Debounced so a bash burst coalesces.
const FS_TOUCHING_TOOLS = new Set([
  "Bash",
  "Edit",
  "Write",
  "MultiEdit",
  "NotebookEdit",
]);
const AUTO_REFRESH_DEBOUNCE_MS = 1500;

const WORKSPACE_PANEL_KEY = "aviary:workspace-panel-open";

/**
 * ChatView — assembles the chat experience for a session.
 *
 * This component is intentionally a thin orchestrator: it composes hooks
 * and child components but contains no business logic of its own. The
 * old 570-line page is fully decomposed into hooks/components under
 * features/chat.
 *
 * The width preference (narrow / comfort / wide) is owned by
 * ChatWidthProvider so the header, banner, message list, and input all
 * stay aligned without prop-drilling.
 */
export function ChatView({ sessionId }: { sessionId: string }) {
  return (
    <ChatWidthProvider>
      <ChatViewInner sessionId={sessionId} />
    </ChatWidthProvider>
  );
}

function ChatViewInner({ sessionId }: { sessionId: string }) {
  const { widthClass } = useChatWidth();

  // Workspace panel state — persisted across sessions, default closed.
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [refreshSignal, setRefreshSignal] = useState(0);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    try {
      setWorkspaceOpen(window.localStorage.getItem(WORKSPACE_PANEL_KEY) === "1");
    } catch {
      // Private-mode / quota errors — fall back to default closed.
    }
  }, []);

  const toggleWorkspace = useCallback(() => {
    setWorkspaceOpen((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(WORKSPACE_PANEL_KEY, next ? "1" : "0");
      } catch {
        // Ignore storage failures — state is still correct in memory.
      }
      return next;
    });
  }, []);

  const handleToolCompleted = useCallback((name: string) => {
    if (!FS_TOUCHING_TOOLS.has(name)) return;
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => {
      refreshTimerRef.current = null;
      setRefreshSignal((n) => n + 1);
    }, AUTO_REFRESH_DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, []);

  const chat = useChatMessages(sessionId, { onToolCompleted: handleToolCompleted });
  const visibleStatus = useConnectionStatus(chat.status);
  const { visionEnabled } = useAgentCapabilities(chat.session?.agent_id ?? undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  const titleEditor = useTitleEditor({
    session: chat.session,
    patchSession: chat.patchSession,
  });

  const exportFns = useChatExport({
    containerRef: scrollRef,
    messages: chat.messages,
    session: chat.session,
  });

  const search = useChatSearch({
    sessionId,
    messages: chat.messages,
    hasMore: chat.hasMore,
    loadEarlier: chat.loadEarlier,
  });

  // Cmd+F / Ctrl+F intercepts the browser's native find (which can't
  // see paginated history anyway) and opens our search bar instead.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "f" || e.key === "F")) {
        e.preventDefault();
        search.openSearch();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [search]);

  const handleSend = useCallback(
    (content: string, attachments?: FileRef[]) => {
      if (chat.send(content, attachments)) {
        titleEditor.setAutoTitleFromMessage(content);
      }
    },
    [chat, titleEditor],
  );

  if (chat.loading) {
    return <LoadingState fullHeight label="Loading session…" />;
  }

  if (!chat.session) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="type-body text-fg-muted">Session not found</p>
        <Link href={routes.agents} className="type-caption text-info hover:opacity-80">
          Back to agents
        </Link>
      </div>
    );
  }

  const isReady = chat.status === "ready";
  const isInputDisabled = !isReady || chat.isStreaming;
  const displayStatus = visibleStatus ?? "ready";
  // Banner shows "Connecting…" only for fresh first-connect intermediates.
  // Reconnecting / offline / disconnected get their own dedicated banners.
  const showConnecting =
    !isReady &&
    visibleStatus !== null &&
    visibleStatus !== "ready" &&
    visibleStatus !== "offline" &&
    visibleStatus !== "disconnected" &&
    visibleStatus !== "reconnecting";

  const activeSearchQuery = search.open ? search.query.trim() : "";

  const canShowWorkspace = workspaceOpen && !!chat.session?.agent_id;

  return (
    <ChatSearchContextProvider
      query={activeSearchQuery}
      currentTargetId={search.currentTargetId}
    >
      <div className="flex h-full bg-canvas">
        <div className="flex h-full flex-1 flex-col min-w-0">
          <ChatHeader
            session={chat.session}
            status={displayStatus}
            hasMessages={chat.messages.length > 0}
            onPrintVisual={exportFns.printVisual}
            onExportText={exportFns.exportText}
            titleEditor={titleEditor}
            workspaceOpen={workspaceOpen}
            onToggleWorkspace={toggleWorkspace}
          />

          <ChatStatusBanner
            status={displayStatus}
            statusMessage={chat.statusMessage}
            showConnecting={showConnecting}
            reconnectIn={chat.reconnectIn}
            onRetryNow={chat.retryNow}
          />

          <ChatSearchBar search={search} />

          <MessageList
            ref={scrollRef}
            messages={chat.messages}
            blocks={chat.blocks}
            isStreaming={chat.isStreaming}
            isReady={isReady}
            hasMore={chat.hasMore}
            loadingEarlier={chat.loadingEarlier}
            onLoadEarlier={chat.loadEarlier}
            highlightedTargetId={search.currentTargetId}
            searchQuery={activeSearchQuery}
          />

          <div className="shrink-0 border-t border-white/[0.06] px-6 py-4">
            <div className={`mx-auto ${widthClass} space-y-2`}>
              {chat.todos.length > 0 && <TodoPanel todos={chat.todos} />}
              <ChatInput
                onSend={handleSend}
                onCancel={chat.cancel}
                disabled={isInputDisabled}
                isStreaming={chat.isStreaming}
                canCancel={chat.canCancel}
                placeholder={
                  !isReady ? "Waiting for agent…" : chat.isStreaming ? "Agent is responding…" : undefined
                }
                agentId={chat.session.agent_id ?? undefined}
                visionEnabled={visionEnabled}
                restoreDraft={chat.restoreDraft}
                onDraftRestored={chat.clearRestoreDraft}
              />
            </div>
          </div>
        </div>

        {canShowWorkspace && (
          <WorkspacePanel
            sessionId={sessionId}
            onClose={toggleWorkspace}
            refreshSignal={refreshSignal}
          />
        )}
      </div>
    </ChatSearchContextProvider>
  );
}
