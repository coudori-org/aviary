"use client";

import { useChatMessages } from "@/features/chat/hooks/use-chat-messages";
import { useConnectionStatus } from "@/features/chat/hooks/use-connection-status";
import { ChatWidthProvider } from "@/features/chat/hooks/use-chat-width";
import { ChatStatusBanner } from "./chat-status-banner";
import { MessageList } from "./message-list/message-list";
import { LoadingState } from "@/components/feedback/loading-state";

/**
 * ChatTranscript — self-contained history + live-stream renderer for one
 * session. Give it a `sessionId` and it drives the WebSocket, restores
 * paginated history, and renders the same MessageList the chat page uses.
 *
 * Used in two places:
 *   1. The chat agent conversation page (wrapped by ChatView which adds
 *      the header, search, and input chrome).
 *   2. The workflow inspector's agent_step card — read-only; the session
 *      is a first-class workflow-origin session the worker created and
 *      emitted via the node_status event's `session_id` field.
 *
 * ``live`` (default true) lets a caller opt out of the WebSocket
 * subscription when it knows no further events will arrive — e.g. the
 * workflow inspector viewing a step that already completed. Skips the
 * connection entirely (no retries on a closed / missing session) and
 * just renders the REST-loaded history.
 *
 * Intentionally not parameterised by "read-only" — input / header live
 * outside this component. Callers that want those wrap it with the
 * chat-view chrome.
 */
export function ChatTranscript({
  sessionId, live = true,
}: { sessionId: string; live?: boolean }) {
  // Keying on sessionId forces a clean remount when the caller switches
  // which session we're showing — critical inside the workflow inspector,
  // where clicking from node A's card to node B's card hands us a new
  // sessionId on the SAME component position. Without the key, React
  // reconciles in place and keeps internal hook state (streaming blocks,
  // isStreaming flag, subscription refs), so B's live chunks pile on top
  // of A's leftovers and the user sees both runs' events at once.
  return (
    <ChatWidthProvider>
      <ChatTranscriptInner key={sessionId} sessionId={sessionId} live={live} />
    </ChatWidthProvider>
  );
}

function ChatTranscriptInner({ sessionId, live }: { sessionId: string; live: boolean }) {
  const chat = useChatMessages(sessionId, { live });
  const visibleStatus = useConnectionStatus(chat.status);

  if (chat.loading) {
    return <LoadingState fullHeight label="Loading session…" />;
  }
  if (!chat.session) {
    return (
      <div className="flex h-full items-center justify-center type-body text-fg-muted">
        Session not found
      </div>
    );
  }

  // Non-live mode (terminal session view) — no WS, so the `connecting`
  // the hook reports is an artefact of never having opened one. Treat
  // the transcript as fully ready so the status banner stays silent.
  const isReady = !live || chat.status === "ready";
  const displayStatus = !live ? "ready" : (visibleStatus ?? "ready");
  const showConnecting =
    live &&
    !isReady &&
    visibleStatus !== null &&
    visibleStatus !== "ready" &&
    visibleStatus !== "offline" &&
    visibleStatus !== "disconnected" &&
    visibleStatus !== "reconnecting";

  return (
    <div className="flex h-full flex-col">
      <ChatStatusBanner
        status={displayStatus}
        statusMessage={chat.statusMessage}
        showConnecting={showConnecting}
        reconnectIn={chat.reconnectIn}
        onRetryNow={chat.retryNow}
      />
      <MessageList
        messages={chat.messages}
        blocks={chat.blocks}
        isStreaming={chat.isStreaming}
        isReady={isReady}
        hasMore={chat.hasMore}
        loadingEarlier={chat.loadingEarlier}
        onLoadEarlier={chat.loadEarlier}
        // Workflow sessions give each run a fresh SDK workspace — the
        // transcript above an error/cancelled turn is preserved but not
        // in-context for the resumed turn. Chat sessions keep history
        // across retries, so the divider only turns on here.
        showRestartDividers={!!chat.session.workflow_run_id}
      />
    </div>
  );
}
