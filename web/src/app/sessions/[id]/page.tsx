"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { MessageBubble } from "@/components/chat/message-bubble";
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
  connecting: "Connecting...",
  provisioning: "Provisioning namespace...",
  spawning: "Starting agent pod...",
  waiting: "Waiting for agent to be ready...",
  ready: "Ready",
  offline: "Offline",
  disconnected: "Disconnected",
};

const STATUS_COLORS: Record<ConnectionStatus, string> = {
  connecting: "bg-yellow-500",
  provisioning: "bg-yellow-500",
  spawning: "bg-yellow-500",
  waiting: "bg-yellow-500",
  ready: "bg-green-500",
  offline: "bg-red-500",
  disconnected: "bg-gray-400",
};

export default function ChatPage() {
  const { user, isLoading } = useAuth();
  const params = useParams();
  const router = useRouter();
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

  // Auto-scroll to bottom
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, streamingContent]);

  // Load session data
  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
      return;
    }
    if (!user) return;

    apiFetch<SessionDetail>(`/sessions/${params.id}`)
      .then((data) => {
        setSession(data.session);
        setMessages(data.messages);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user, isLoading, params.id, router]);

  // Connect WebSocket (guard against React Strict Mode double-mount)
  const wsConnected = useRef(false);
  useEffect(() => {
    if (!session || !user) return;
    if (wsConnected.current) return;
    wsConnected.current = true;

    setConnStatus("connecting");
    setStatusMessage(null);

    const ws = createSessionWebSocket(
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
            // Reset ref and state BEFORE adding message
            streamingRef.current = "";
            setStreamingContent("");
            if (finalContent) {
              const agentMsg: Message = {
                id: msg.messageId,
                session_id: session.id,
                sender_type: "agent",
                content: finalContent,
                metadata: {},
                created_at: new Date().toISOString(),
              };
              setMessages((msgs) => [...msgs, agentMsg]);
            }
            setIsStreaming(false);
            break;
          }
          case "error":
            streamingRef.current = "";
            setStreamingContent("");
            setIsStreaming(false);
            setMessages((msgs) => [
              ...msgs,
              {
                id: crypto.randomUUID(),
                session_id: session.id,
                sender_type: "agent",
                content: `Error: ${msg.message}`,
                metadata: {},
                created_at: new Date().toISOString(),
              },
            ]);
            break;
        }
      },
      () => {
        // On close
      }
    );

    wsRef.current = ws;

    return () => {
      ws.close();
      wsConnected.current = false;
    };
  }, [session, user]);

  const handleSend = useCallback(
    (content: string) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !isReady)
        return;

      // Ensure clean state before new turn
      streamingRef.current = "";
      setStreamingContent("");

      const userMsg: Message = {
        id: crypto.randomUUID(),
        session_id: session!.id,
        sender_type: "user",
        sender_id: user!.id,
        content,
        metadata: {},
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsStreaming(true);

      wsRef.current.send(JSON.stringify({ type: "message", content }));
    },
    [session, user, isReady]
  );

  if (isLoading || loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-muted-foreground">Session not found</div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="flex items-center justify-between border-b px-6 py-3">
        <div>
          <Link
            href={`/agents/${session.agent_id}`}
            className="text-sm text-muted-foreground hover:underline"
          >
            &larr; Back to agent
          </Link>
          <h1 className="text-lg font-semibold">
            {session.title || "New Session"}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${STATUS_COLORS[connStatus]}`}
          />
          <span className="text-xs text-muted-foreground">
            {STATUS_LABELS[connStatus]}
          </span>
        </div>
      </header>

      {/* Status banner when not ready */}
      {!isReady && connStatus !== "disconnected" && (
        <div className="flex items-center justify-center gap-2 border-b bg-muted/50 px-4 py-2">
          <svg
            className="h-4 w-4 animate-spin text-muted-foreground"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span className="text-sm text-muted-foreground">
            {STATUS_LABELS[connStatus]}
            {statusMessage && ` — ${statusMessage}`}
          </span>
        </div>
      )}

      {/* Offline banner */}
      {connStatus === "offline" && (
        <div className="flex items-center justify-center gap-2 border-b bg-destructive/10 px-4 py-2">
          <span className="text-sm text-destructive">
            Agent is offline{statusMessage && `: ${statusMessage}`}
          </span>
        </div>
      )}

      {/* Disconnected banner */}
      {connStatus === "disconnected" && (
        <div className="flex items-center justify-center gap-2 border-b bg-muted px-4 py-2">
          <span className="text-sm text-muted-foreground">
            Connection lost. Refresh the page to reconnect.
          </span>
        </div>
      )}

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              currentUserId={user?.id}
            />
          ))}

          {/* Streaming indicator */}
          {streamingContent && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-lg bg-muted px-4 py-2 text-sm">
                <div className="whitespace-pre-wrap break-words">
                  {streamingContent}
                  <span className="inline-block w-2 animate-pulse">|</span>
                </div>
              </div>
            </div>
          )}

          {isStreaming && !streamingContent && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-muted px-4 py-2 text-sm text-muted-foreground">
                Thinking...
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="border-t p-4">
        <div className="mx-auto max-w-3xl">
          <ChatInput
            onSend={handleSend}
            disabled={isInputDisabled}
            placeholder={
              !isReady
                ? "Waiting for agent to be ready..."
                : isStreaming
                  ? "Agent is responding..."
                  : "Type a message... (Shift+Enter for newline)"
            }
          />
        </div>
      </div>
    </div>
  );
}
