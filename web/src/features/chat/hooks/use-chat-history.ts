"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { http } from "@/lib/http";
import type { FileRef, Message, Session } from "@/types";

interface SessionDetail {
  session: Session;
  messages: Message[];
  has_more: boolean;
}

interface MessagePage {
  messages: Message[];
  has_more: boolean;
}

export interface RestoreDraft {
  content: string;
  attachments?: FileRef[];
  error?: string;
}

/**
 * Owns the message list + session metadata: initial fetch, pagination,
 * incremental updates from the WS event handler, and the restore-draft
 * (for pre-query error rollback). Returns writer callbacks the caller
 * uses from its WS switch — keeps the chat-messages hook thin.
 */
export function useChatHistory(sessionId: string) {
  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [restoreDraft, setRestoreDraft] = useState<RestoreDraft | null>(null);

  // Guards stacked loadEarlier if the sentinel briefly re-intersects
  // before React commits the prepended state.
  const loadingEarlierRef = useRef(false);

  const reloadHistory = useCallback(async () => {
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
    return () => { cancelled = true; };
  }, [sessionId]);

  const loadEarlier = useCallback(async () => {
    if (loadingEarlierRef.current || !hasMore) return;
    const oldest = messages[0];
    if (!oldest) return;
    loadingEarlierRef.current = true;
    setLoadingEarlier(true);
    try {
      const page = await http.get<MessagePage>(
        `/sessions/${sessionId}/messages?before=${encodeURIComponent(oldest.created_at)}`,
      );
      setMessages((prev) => {
        // Dedupe by id — cursor boundary can repeat the exact message.
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

  const patchSession = useCallback((patch: Partial<Session>) => {
    setSession((prev) => (prev ? { ...prev, ...patch } : prev));
  }, []);

  const appendMessage = useCallback((msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const appendUniqueMessage = useCallback((msg: Message) => {
    setMessages((prev) =>
      prev.some((m) => m.id === msg.id) ? prev : [...prev, msg],
    );
  }, []);

  const dropTransientMessages = useCallback(() => {
    setMessages((prev) => prev.filter((m) => !m.metadata?.transient));
  }, []);

  /** For pre-query rollback: remove the last user message, stash its
   *  content into `restoreDraft` so the input can repopulate, and leave
   *  a transient error bubble in its place. */
  const rollbackLastUserMessage = useCallback((errorText: string) => {
    setMessages((prev) => {
      const lastUserIdx = [...prev].reverse().findIndex((m) => m.sender_type === "user");
      if (lastUserIdx === -1) return prev;
      const idx = prev.length - 1 - lastUserIdx;
      const removed = prev[idx];
      setRestoreDraft({
        content: removed.content,
        attachments: removed.metadata?.attachments as FileRef[] | undefined,
      });
      return [
        ...prev.slice(0, idx),
        ...prev.slice(idx + 1),
        {
          id: crypto.randomUUID(),
          session_id: sessionId,
          sender_type: "user",
          content: errorText,
          metadata: { transient: true },
          created_at: new Date().toISOString(),
        },
      ];
    });
  }, [sessionId]);

  const clearRestoreDraft = useCallback(() => setRestoreDraft(null), []);

  return {
    session,
    messages,
    loading,
    hasMore,
    loadingEarlier,
    loadEarlier,
    reloadHistory,
    patchSession,
    appendMessage,
    appendUniqueMessage,
    dropTransientMessages,
    rollbackLastUserMessage,
    restoreDraft,
    clearRestoreDraft,
  };
}
