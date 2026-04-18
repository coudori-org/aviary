"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { http } from "@/lib/http";
import { sendWsMessage } from "@/lib/ws";
import type { WSMessage } from "@/lib/ws";
import type { FileRef, Message, Session } from "@/types";
import { useStreamingBlocks } from "./use-streaming-blocks";
import { useSessionWebSocket } from "./use-session-websocket";

interface SessionDetail {
  session: Session;
  messages: Message[];
  has_more: boolean;
}

interface MessagePage {
  messages: Message[];
  has_more: boolean;
}


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
  /** Content to restore into the input after a rollback error. */
  restoreDraft: { content: string; attachments?: FileRef[]; error?: string } | null;
  clearRestoreDraft: () => void;
}

interface UseChatMessagesOptions {
  /** Open the WS subscription for live events. Default true. Set false
   *  when the caller already knows the session is in a terminal state
   *  (e.g. the workflow inspector viewing a completed step) — skips the
   *  connection and its reconnect loop, just renders REST history. */
  live?: boolean;
}

/**
 * useChatMessages — composes initial session fetch, WS subscription, streaming
 * block accumulation, and persistence of completed messages.
 */
export function useChatMessages(
  sessionId: string, options: UseChatMessagesOptions = {},
): UseChatMessagesResult {
  const live = options.live ?? true;
  const { refreshUser } = useAuth();
  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  // Set when the supervisor publishes `stream_started` — that event is our
  // confirmation the request was accepted. The abort button only goes active
  // once we have this id, and cancel sends it back so the server aborts the
  // specific stream (not whatever is latest on the session).
  const [streamId, setStreamId] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [restoreDraft, setRestoreDraft] = useState<{ content: string; attachments?: FileRef[]; error?: string } | null>(null);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const blockState = useStreamingBlocks();
  // `reset` is useCallback'd with an empty dep array, so capturing it
  // into a stable local alias here keeps it usable in other effects'
  // dep arrays without retriggering them on every render.
  const resetBlocks = blockState.reset;

  // Guards against stacked loadEarlier calls if the sentinel briefly
  // re-intersects before React commits the prepended state.
  const loadingEarlierRef = useRef(false);

  const reloadHistory = useCallback(async () => {
    // Reloads only the most recent page — any "show earlier" expansion is
    // lost on purpose, since the WS disconnect case it's called from is
    // effectively a fresh start.
    const data = await http.get<SessionDetail>(`/sessions/${sessionId}`);
    setMessages(data.messages);
    setHasMore(data.has_more);
    return data;
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setMessages([]);
    setHasMore(false);
    // Drop any streaming state carried over from a prior sessionId —
    // ChatTranscript keys on sessionId so this is mostly defensive, but
    // it also covers a fringe race where the previous session's WS
    // closed (live→false) before the terminal `done` event could reset
    // the blocks: without this, those blocks would persist into the
    // next render.
    resetBlocks();
    setIsStreaming(false);
    setStreamId(null);
    http
      .get<SessionDetail>(`/sessions/${sessionId}`)
      .then((data) => {
        if (cancelled) return;
        setSession(data.session);
        setMessages(data.messages);
        setHasMore(data.has_more);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, resetBlocks]);

  const loadEarlier = useCallback(async () => {
    if (loadingEarlierRef.current) return;
    if (!hasMore) return;
    const oldest = messages[0];
    if (!oldest) return;
    loadingEarlierRef.current = true;
    setLoadingEarlier(true);
    try {
      const page = await http.get<MessagePage>(
        `/sessions/${sessionId}/messages?before=${encodeURIComponent(oldest.created_at)}`,
      );
      setMessages((prev) => {
        // Dedupe by id in case a message lands exactly at the cursor boundary.
        const existingIds = new Set(prev.map((m) => m.id));
        const newOnes = page.messages.filter((m) => !existingIds.has(m.id));
        return [...newOnes, ...prev];
      });
      setHasMore(page.has_more);
    } finally {
      setLoadingEarlier(false);
      loadingEarlierRef.current = false;
    }
  }, [sessionId, hasMore, messages]);

  // Stable handler that avoids stale closures via refs
  const blockStateRef = useRef(blockState);
  useEffect(() => {
    blockStateRef.current = blockState;
  }, [blockState]);

  const handleMessage = useCallback(
    (msg: WSMessage) => {
      const bs = blockStateRef.current;
      switch (msg.type) {
        case "status":
          if (msg.status === "disconnected") {
            // Flush in-flight state and reload from DB so any partially saved
            // response surfaces correctly.
            bs.reset();
            setIsStreaming(false);
            setStreamId(null);
            void reloadHistory();
          }
          break;

        case "user_message":
          setIsStreaming(true);
          setMessages((prev) => [
            ...prev,
            {
              id: msg.messageId,
              session_id: sessionId,
              sender_type: "user",
              sender_id: msg.sender_id,
              content: msg.content,
              metadata: msg.attachments ? { attachments: msg.attachments } : {},
              created_at: new Date().toISOString(),
            },
          ]);
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
            setMessages((prev) => {
              if (prev.some((m) => m.id === msg.messageId)) return prev;
              return [
                ...prev,
                {
                  id: msg.messageId,
                  session_id: sessionId,
                  sender_type: "agent",
                  content: finalContent,
                  metadata,
                  created_at: new Date().toISOString(),
                },
              ];
            });
          }
          setIsStreaming(false);
          setStreamId(null);
          break;
        }

        case "error": {
          // "Session expired" is the backend's signal that the auth
          // session is dead — bounce through refreshUser so AuthGuard
          // sends the user to /login instead of leaving them on a
          // half-broken chat with a dangling error bubble.
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
            const errorMessageId = msg.messageId;
            setMessages((prev) => {
              if (prev.some((m) => m.id === errorMessageId)) return prev;
              return [
                ...prev,
                {
                  id: errorMessageId,
                  session_id: sessionId,
                  sender_type: "agent",
                  content: partialContent,
                  metadata: { blocks: allBlocks, error: true },
                  created_at: new Date().toISOString(),
                },
              ];
            });
            setIsStreaming(false);
            setStreamId(null);
            break;
          }

          bs.reset();
          setIsStreaming(false);
          setStreamId(null);

          // Pre-query failure: backend rolled back the user message from DB.
          // Restore the content to the input field so the user can retry,
          // and show a transient error that disappears on next successful send.
          if (msg.rollback_message_id) {
            setMessages((prev) => {
              const lastUserIdx = [...prev].reverse().findIndex((m) => m.sender_type === "user");
              if (lastUserIdx === -1) return prev;
              const idx = prev.length - 1 - lastUserIdx;
              const removed = prev[idx];
              setRestoreDraft({
                content: removed.content,
                attachments: removed.metadata?.attachments as FileRef[] | undefined,
              });
              // Replace the user message with a transient error bubble
              return [
                ...prev.slice(0, idx),
                ...prev.slice(idx + 1),
                {
                  id: crypto.randomUUID(),
                  session_id: sessionId,
                  sender_type: "user",
                  content: msg.message,
                  metadata: { transient: true },
                  created_at: new Date().toISOString(),
                },
              ];
            });
            break;
          }
          setMessages((prev) => [
            ...prev,
            {
              id: crypto.randomUUID(),
              session_id: sessionId,
              sender_type: "agent",
              content: msg.message,
              metadata: { error: true },
              created_at: new Date().toISOString(),
            },
          ]);
          break;
        }

        case "replay_start":
          setIsStreaming(true);
          bs.reset();
          break;

        case "replay_end":
          break;

        case "cancelled": {
          // Don't finalize — leave any running tools as-is so they show cancelled state
          const partialContent = bs.flattenText();
          const partialBlocks = bs.getBlocksMeta();
          const cancelMeta: Record<string, unknown> = { cancelled: true };
          if (partialBlocks.length > 0) cancelMeta.blocks = partialBlocks;
          bs.reset();
          if (partialContent || partialBlocks.length > 0) {
            const cancelledId = msg.messageId || crypto.randomUUID();
            setMessages((prev) => {
              if (prev.some((m) => m.id === cancelledId)) return prev;
              return [
                ...prev,
                {
                  id: cancelledId,
                  session_id: sessionId,
                  sender_type: "agent",
                  content: partialContent,
                  metadata: cancelMeta,
                  created_at: new Date().toISOString(),
                },
              ];
            });
          }
          setIsStreaming(false);
          setStreamId(null);
          break;
        }

        case "stream_complete":
          setMessages((prev) => {
            if (prev.some((m) => m.id === msg.messageId)) return prev;
            return [
              ...prev,
              {
                id: msg.messageId,
                session_id: sessionId,
                sender_type: "agent",
                content: msg.content,
                metadata: {},
                created_at: new Date().toISOString(),
              },
            ];
          });
          setIsStreaming(false);
          break;
      }
    },
    [sessionId, reloadHistory, refreshUser],
  );

  const { ws, status, statusMessage, reconnectIn, retryNow } = useSessionWebSocket({
    sessionId,
    enabled: !!session && live,
    onMessage: handleMessage,
    // After every successful (re)connect, refresh history so anything that
    // happened during the offline window appears in the UI.
    onReconnected: () => {
      void reloadHistory();
    },
  });

  const send = useCallback(
    (content: string, attachments?: FileRef[]) => {
      if (status !== "ready") return false;
      setMessages((prev) => prev.filter((m) => !m.metadata?.transient));
      setRestoreDraft(null);
      const msg: Record<string, unknown> = { type: "message", content };
      if (attachments?.length) msg.attachments = attachments;
      const ok = sendWsMessage(ws, msg);
      if (ok) setIsStreaming(true);
      return ok;
    },
    [ws, status],
  );

  const clearRestoreDraft = useCallback(() => setRestoreDraft(null), []);

  const cancel = useCallback(() => {
    if (!streamId) return;
    sendWsMessage(ws, { type: "cancel", stream_id: streamId });
  }, [ws, streamId]);

  const patchSession = useCallback((patch: Partial<Session>) => {
    setSession((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  return {
    session,
    messages,
    loading,
    isStreaming,
    hasMore,
    loadingEarlier,
    loadEarlier,
    blocks: blockState.blocks,
    todos: blockState.todos,
    status,
    statusMessage,
    reconnectIn,
    retryNow,
    send,
    cancel,
    canCancel: streamId !== null,
    patchSession,
    restoreDraft,
    clearRestoreDraft,
  };
}
