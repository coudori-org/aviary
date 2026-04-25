"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { sendWsMessage } from "@/lib/ws";
import type { WSMessage } from "@/lib/ws";
import type { FileRef, Message, Session } from "@/types";
import { useStreamingBlocks } from "./use-streaming-blocks";
import { useSessionWebSocket } from "./use-session-websocket";
import { useChatHistory, type RestoreDraft } from "./use-chat-history";

interface UseChatMessagesResult {
  session: Session | null;
  messages: Message[];
  loading: boolean;
  isStreaming: boolean;
  hasMore: boolean;
  loadingEarlier: boolean;
  loadEarlier: () => Promise<void>;
  blocks: ReturnType<typeof useStreamingBlocks>["blocks"];
  todos: ReturnType<typeof useStreamingBlocks>["todos"];
  status: ReturnType<typeof useSessionWebSocket>["status"];
  statusMessage: ReturnType<typeof useSessionWebSocket>["statusMessage"];
  reconnectIn: ReturnType<typeof useSessionWebSocket>["reconnectIn"];
  retryNow: ReturnType<typeof useSessionWebSocket>["retryNow"];
  send: (content: string, attachments?: FileRef[]) => boolean;
  cancel: () => void;
  canCancel: boolean;
  patchSession: (patch: Partial<Session>) => void;
  restoreDraft: RestoreDraft | null;
  clearRestoreDraft: () => void;
}

interface UseChatMessagesOptions {
  /** Open the WS subscription for live events. Default true. Set false
   *  when the caller knows the session is terminal (e.g. workflow
   *  inspector viewing a completed step) — skips the reconnect loop. */
  live?: boolean;
  /** Notified when any tool completes. The workspace file-tree panel uses
   *  this to auto-refresh after filesystem-touching tools (Bash/Edit/Write/…). */
  onToolCompleted?: (toolName: string) => void;
}

/**
 * Orchestrates chat-session UX by composing three focused hooks:
 *   - useChatHistory       — REST messages + pagination + rollback
 *   - useStreamingBlocks   — block accumulator driven by WS events
 *   - useSessionWebSocket  — WS lifecycle + reconnect
 */
export function useChatMessages(
  sessionId: string, options: UseChatMessagesOptions = {},
): UseChatMessagesResult {
  const live = options.live ?? true;
  const { refreshUser } = useAuth();
  const history = useChatHistory(sessionId);
  const blockState = useStreamingBlocks({ onToolCompleted: options.onToolCompleted });
  const [isStreaming, setIsStreaming] = useState(false);
  // Set when supervisor publishes ``stream_started`` — confirms the request
  // was accepted. Abort button needs this id to target the specific stream.
  const [streamId, setStreamId] = useState<string | null>(null);

  // Drop streaming state on session change; ChatView keys on sessionId so
  // this is mostly defensive, but also covers the fringe race where the
  // previous session's WS closed (live=false) before the terminal event
  // could reset the blocks.
  const resetBlocks = blockState.reset;
  useEffect(() => {
    resetBlocks();
    setIsStreaming(false);
    setStreamId(null);
  }, [sessionId, resetBlocks]);

  // Stable handler via ref — new setters would otherwise retrigger the
  // WS subscription every render.
  const blockStateRef = useRef(blockState);
  useEffect(() => { blockStateRef.current = blockState; }, [blockState]);

  const reloadHistory = history.reloadHistory;

  const handleMessage = useCallback(
    (msg: WSMessage) => {
      const bs = blockStateRef.current;
      switch (msg.type) {
        case "status":
          if (msg.status === "disconnected") {
            // Flush in-flight state and reload from DB so any partially
            // saved response surfaces.
            bs.reset();
            setIsStreaming(false);
            setStreamId(null);
            void reloadHistory();
          }
          break;

        case "user_message":
          setIsStreaming(true);
          history.appendMessage({
            id: msg.messageId,
            session_id: sessionId,
            sender_type: "user",
            sender_id: msg.sender_id,
            content: msg.content,
            metadata: msg.attachments ? { attachments: msg.attachments } : {},
            created_at: new Date().toISOString(),
          });
          break;

        case "stream_started":
          setIsStreaming(true);
          setStreamId(msg.stream_id);
          break;

        case "thinking":
        case "chunk":
        case "tool_use":
        case "tool_result":
        case "tool_progress":
          bs.handleMessage(msg);
          break;

        case "done": {
          bs.finalize();
          const finalContent = bs.flattenText();
          const savedBlocks = bs.getBlocksMeta();
          const metadata: Record<string, unknown> =
            savedBlocks.length > 0 ? { blocks: savedBlocks } : {};
          bs.reset();
          if (finalContent || savedBlocks.length > 0) {
            history.appendUniqueMessage({
              id: msg.messageId,
              session_id: sessionId,
              sender_type: "agent",
              content: finalContent,
              metadata,
              created_at: new Date().toISOString(),
            });
          }
          setIsStreaming(false);
          setStreamId(null);
          break;
        }

        case "error": {
          // "Session expired" = auth session dead. Bounce through refreshUser
          // so AuthGuard sends the user to /login instead of leaving them on
          // a half-broken chat with a dangling error bubble.
          if (msg.message?.toLowerCase().includes("session expired")) {
            bs.reset();
            setIsStreaming(false);
            setStreamId(null);
            void refreshUser();
            break;
          }

          // messageId present → backend persisted; mirror locally so the
          // bubble shows without waiting for a history reload.
          if (msg.messageId) {
            bs.finalize();
            const partialContent = bs.flattenText();
            const partialBlocks = bs.getBlocksMeta();
            const allBlocks: Record<string, unknown>[] = [
              ...partialBlocks,
              { type: "error", message: msg.message },
            ];
            bs.reset();
            history.appendUniqueMessage({
              id: msg.messageId,
              session_id: sessionId,
              sender_type: "agent",
              content: partialContent,
              metadata: { blocks: allBlocks, error: true },
              created_at: new Date().toISOString(),
            });
            setIsStreaming(false);
            setStreamId(null);
            break;
          }

          bs.reset();
          setIsStreaming(false);
          setStreamId(null);

          // Pre-query failure: backend rolled back the user message. Restore
          // content to the input so the user can retry, show a transient
          // error bubble.
          if (msg.rollback_message_id) {
            history.rollbackLastUserMessage(msg.message);
            break;
          }
          history.appendMessage({
            id: crypto.randomUUID(),
            session_id: sessionId,
            sender_type: "agent",
            content: msg.message,
            metadata: { error: true },
            created_at: new Date().toISOString(),
          });
          break;
        }

        case "replay_start":
          setIsStreaming(true);
          bs.reset();
          break;

        case "replay_end":
          break;

        case "cancelled": {
          // Don't finalize — leave running tools as-is so they render cancelled.
          const partialContent = bs.flattenText();
          const partialBlocks = bs.getBlocksMeta();
          const cancelMeta: Record<string, unknown> = { cancelled: true };
          if (partialBlocks.length > 0) cancelMeta.blocks = partialBlocks;
          bs.reset();
          if (partialContent || partialBlocks.length > 0) {
            history.appendUniqueMessage({
              id: msg.messageId || crypto.randomUUID(),
              session_id: sessionId,
              sender_type: "agent",
              content: partialContent,
              metadata: cancelMeta,
              created_at: new Date().toISOString(),
            });
          }
          setIsStreaming(false);
          setStreamId(null);
          break;
        }

        case "stream_complete":
          history.appendUniqueMessage({
            id: msg.messageId,
            session_id: sessionId,
            sender_type: "agent",
            content: msg.content,
            metadata: {},
            created_at: new Date().toISOString(),
          });
          setIsStreaming(false);
          break;
      }
    },
    [sessionId, reloadHistory, refreshUser, history],
  );

  const { ws, status, statusMessage, reconnectIn, retryNow } = useSessionWebSocket({
    sessionId,
    enabled: !!history.session && live,
    onMessage: handleMessage,
    // After every successful (re)connect, refresh history so anything that
    // happened during the offline window appears in the UI.
    onReconnected: () => { void reloadHistory(); },
  });

  const send = useCallback(
    (content: string, attachments?: FileRef[]) => {
      if (status !== "ready") return false;
      history.dropTransientMessages();
      history.clearRestoreDraft();
      const msg: Record<string, unknown> = { type: "message", content };
      if (attachments?.length) msg.attachments = attachments;
      const ok = sendWsMessage(ws, msg);
      if (ok) setIsStreaming(true);
      return ok;
    },
    [ws, status, history],
  );

  const cancel = useCallback(() => {
    if (!streamId) return;
    sendWsMessage(ws, { type: "cancel", stream_id: streamId });
  }, [ws, streamId]);

  return {
    session: history.session,
    messages: history.messages,
    loading: history.loading,
    isStreaming,
    hasMore: history.hasMore,
    loadingEarlier: history.loadingEarlier,
    loadEarlier: history.loadEarlier,
    blocks: blockState.blocks,
    todos: blockState.todos,
    status,
    statusMessage,
    reconnectIn,
    retryNow,
    send,
    cancel,
    canCancel: streamId !== null,
    patchSession: history.patchSession,
    restoreDraft: history.restoreDraft,
    clearRestoreDraft: history.clearRestoreDraft,
  };
}
