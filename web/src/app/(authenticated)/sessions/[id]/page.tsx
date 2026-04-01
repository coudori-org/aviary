"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { MessageBubble } from "@/components/chat/message-bubble";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { ChatInput } from "@/components/chat/chat-input";
import { apiFetch } from "@/lib/api";
import {
  createSessionWebSocket,
  type ConnectionStatus,
  type WSMessage,
} from "@/lib/websocket";
import type { Message, Session } from "@/types";

interface SessionDetail {
  session: Session;
  messages: Message[];
}

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: "Connecting",
  provisioning: "Setting up environment",
  spawning: "Starting agent",
  waiting: "Almost ready",
  ready: "Online",
  offline: "Offline",
  disconnected: "Disconnected",
};

const STATUS_STYLES: Record<ConnectionStatus, { dot: string; text: string }> = {
  connecting: { dot: "bg-warning animate-pulse-soft", text: "text-warning" },
  provisioning: { dot: "bg-warning animate-pulse-soft", text: "text-warning" },
  spawning: { dot: "bg-warning animate-pulse-soft", text: "text-warning" },
  waiting: { dot: "bg-warning animate-pulse-soft", text: "text-warning" },
  ready: { dot: "bg-success", text: "text-success" },
  offline: { dot: "bg-destructive", text: "text-destructive" },
  disconnected: { dot: "bg-muted-foreground/50", text: "text-muted-foreground" },
};

export default function ChatPage() {
  const { user } = useAuth();
  const params = useParams();
  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [connStatus, setConnStatus] = useState<ConnectionStatus>("connecting");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const streamingRef = useRef("");

  const isReady = connStatus === "ready";
  const isInputDisabled = !isReady || isStreaming;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streamingContent]);

  useEffect(() => {
    if (!user) return;
    apiFetch<SessionDetail>(`/sessions/${params.id}`)
      .then((data) => { setSession(data.session); setMessages(data.messages); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user, params.id]);

  const wsConnected = useRef(false);
  useEffect(() => {
    if (!session || !user) return;
    if (wsConnected.current) return;
    wsConnected.current = true;

    setConnStatus("connecting");
    setStatusMessage(null);

    let cancelled = false;

    createSessionWebSocket(
      session.id,
      (msg: WSMessage) => {
        switch (msg.type) {
          case "status":
            setConnStatus(msg.status);
            setStatusMessage(msg.message || null);
            break;
          case "chunk":
            streamingRef.current += msg.content;
            setStreamingContent(streamingRef.current);
            break;
          case "tool_use":
            streamingRef.current += `\n[Tool: ${msg.name}]\n`;
            setStreamingContent(streamingRef.current);
            break;
          case "done": {
            const finalContent = streamingRef.current;
            streamingRef.current = "";
            setStreamingContent("");
            if (finalContent) {
              setMessages((msgs) => {
                if (msgs.some((m) => m.id === msg.messageId)) return msgs;
                return [...msgs, {
                  id: msg.messageId, session_id: session.id, sender_type: "agent",
                  content: finalContent, metadata: {}, created_at: new Date().toISOString(),
                }];
              });
            }
            setIsStreaming(false);
            break;
          }
          case "error":
            streamingRef.current = "";
            setStreamingContent("");
            setIsStreaming(false);
            setMessages((msgs) => [...msgs, {
              id: crypto.randomUUID(), session_id: session.id, sender_type: "agent",
              content: `Error: ${msg.message}`, metadata: {}, created_at: new Date().toISOString(),
            }]);
            break;
          case "replay_start":
            // Reconnected during active stream — replay buffered chunks
            setIsStreaming(true);
            streamingRef.current = "";
            setStreamingContent("");
            break;
          case "replay_end":
            // Replay complete, now receiving live chunks via pub/sub
            break;
          case "cancelled": {
            const partialContent = streamingRef.current;
            streamingRef.current = "";
            setStreamingContent("");
            if (partialContent) {
              const cancelledId = msg.messageId || crypto.randomUUID();
              setMessages((msgs) => {
                if (msgs.some((m) => m.id === cancelledId)) return msgs;
                return [...msgs, {
                  id: cancelledId, session_id: session.id, sender_type: "agent",
                  content: partialContent, metadata: {}, created_at: new Date().toISOString(),
                }];
              });
            }
            setIsStreaming(false);
            break;
          }
          case "stream_complete":
            // Agent finished responding while we were on another page
            setMessages((msgs) => {
              if (msgs.some((m) => m.id === msg.messageId)) return msgs;
              return [...msgs, {
                id: msg.messageId, session_id: session.id, sender_type: "agent",
                content: msg.content, metadata: {}, created_at: new Date().toISOString(),
              }];
            });
            setIsStreaming(false);
            break;
        }
      },
      () => {}
    ).then((ws) => {
      if (cancelled) { ws.close(); return; }
      wsRef.current = ws;
    });

    return () => { cancelled = true; wsRef.current?.close(); wsConnected.current = false; };
  }, [session, user]);

  const handleSend = useCallback(
    (content: string) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !isReady) return;
      streamingRef.current = "";
      setStreamingContent("");
      setMessages((prev) => [...prev, {
        id: crypto.randomUUID(), session_id: session!.id, sender_type: "user",
        sender_id: user!.id, content, metadata: {}, created_at: new Date().toISOString(),
      }]);
      setIsStreaming(true);
      wsRef.current.send(JSON.stringify({ type: "message", content }));
    },
    [session, user, isReady]
  );

  const handleCancel = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "cancel" }));
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-muted-foreground">
          <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
          <span className="text-sm">Loading session...</span>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-sm text-muted-foreground">Session not found</p>
        <Link href="/agents" className="text-sm text-primary hover:underline">Back to agents</Link>
      </div>
    );
  }

  const statusStyle = STATUS_STYLES[connStatus];

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="shrink-0 border-b border-border/30 px-6 py-3">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href={`/agents/${session.agent_id}`}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-muted-foreground hover:bg-secondary/80 transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
            </Link>
            <h1 className="text-sm font-semibold text-foreground">{session.title || "New Session"}</h1>
          </div>
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${statusStyle.dot}`} />
            <span className={`text-xs font-medium ${statusStyle.text}`}>{STATUS_LABELS[connStatus]}</span>
          </div>
        </div>
      </header>

      {/* Status banners */}
      {!isReady && connStatus !== "disconnected" && connStatus !== "offline" && (
        <div className="shrink-0 border-b border-warning/10 bg-warning/5 px-6 py-2.5">
          <div className="mx-auto flex max-w-4xl items-center justify-center gap-2">
            <svg className="h-4 w-4 animate-spin text-warning" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            <span className="text-xs text-warning">{STATUS_LABELS[connStatus]}{statusMessage && ` — ${statusMessage}`}</span>
          </div>
        </div>
      )}
      {connStatus === "offline" && (
        <div className="shrink-0 border-b border-destructive/10 bg-destructive/5 px-6 py-2.5">
          <div className="mx-auto flex max-w-4xl items-center justify-center gap-2">
            <span className="text-xs text-destructive">Agent is offline{statusMessage && ` — ${statusMessage}`}</span>
          </div>
        </div>
      )}
      {connStatus === "disconnected" && (
        <div className="shrink-0 border-b border-border/30 bg-secondary/50 px-6 py-2.5">
          <div className="mx-auto flex max-w-4xl items-center justify-center">
            <span className="text-xs text-muted-foreground">Connection lost. Refresh to reconnect.</span>
          </div>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-6 py-6">
          {messages.length === 0 && isReady && !isStreaming && (
            <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
              </div>
              <p className="mt-4 text-sm font-medium text-foreground">Ready to chat</p>
              <p className="mt-1 text-xs text-muted-foreground">Send a message to start the conversation</p>
            </div>
          )}

          <div className="space-y-5">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} currentUserId={user?.id} />
            ))}

            {streamingContent && (
              <div className="flex gap-3 animate-fade-in">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-xs font-semibold text-muted-foreground">AI</div>
                <div className="max-w-[75%]">
                  <div className="rounded-2xl rounded-tl-md bg-chat-agent px-4 py-3 text-[14px] leading-[1.7] text-chat-agent-fg">
                    <div className="markdown-body break-words">
                      <MarkdownContent content={streamingContent} />
                      <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse-soft bg-primary" />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {isStreaming && !streamingContent && (
              <div className="flex gap-3 animate-fade-in">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-xs font-semibold text-muted-foreground">AI</div>
                <div className="rounded-2xl rounded-tl-md bg-chat-agent px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-muted-foreground/50" style={{ animationDelay: "0ms" }} />
                    <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-muted-foreground/50" style={{ animationDelay: "200ms" }} />
                    <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-muted-foreground/50" style={{ animationDelay: "400ms" }} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-border/30 px-6 py-4">
        <div className="mx-auto max-w-4xl">
          <ChatInput
            onSend={handleSend}
            onCancel={handleCancel}
            disabled={isInputDisabled}
            isStreaming={isStreaming}
            placeholder={!isReady ? "Waiting for agent..." : isStreaming ? "Agent is responding..." : undefined}
          />
        </div>
      </div>
    </div>
  );
}
