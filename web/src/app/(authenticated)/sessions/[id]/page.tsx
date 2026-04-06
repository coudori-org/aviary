"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { marked } from "marked";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { MessageBubble } from "@/components/chat/message-bubble";
import { StreamingResponse } from "@/components/chat/streaming-response";
import { useStreamingBlocks } from "@/components/chat/use-streaming-blocks";
import { TodoPanel } from "@/components/chat/todo-panel";
import { ChatInput } from "@/components/chat/chat-input";
import { useSidebar } from "@/components/layout/app-shell";
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

// Statuses that resolve immediately (no delay)
const IMMEDIATE_STATUSES = new Set<ConnectionStatus>(["ready", "offline", "disconnected"]);
const STATUS_SHOW_DELAY = 500; // ms before showing intermediate states

export default function ChatPage() {
  const { user } = useAuth();
  const params = useParams();
  const { updateSessionTitle: updateSidebarTitle } = useSidebar();
  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [connStatus, setConnStatus] = useState<ConnectionStatus>("connecting");
  const [visibleStatus, setVisibleStatus] = useState<ConnectionStatus | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { blocks, todos, handleMessage: handleStreamMsg, reset: resetBlocks, flattenText, getBlocksMeta, finalize } = useStreamingBlocks();

  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editingTitle, setEditingTitle] = useState("");
  const titleInputRef = useRef<HTMLInputElement>(null);

  // Debounce intermediate statuses so fast connections don't flicker
  const statusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (IMMEDIATE_STATUSES.has(connStatus)) {
      if (statusTimerRef.current) clearTimeout(statusTimerRef.current);
      setVisibleStatus(connStatus);
    } else {
      // Only show intermediate status after a delay
      if (!statusTimerRef.current) {
        statusTimerRef.current = setTimeout(() => {
          statusTimerRef.current = null;
          setVisibleStatus(connStatus);
        }, STATUS_SHOW_DELAY);
      }
    }
    return () => {
      if (statusTimerRef.current) {
        clearTimeout(statusTimerRef.current);
        statusTimerRef.current = null;
      }
    };
  }, [connStatus]);

  const isReady = connStatus === "ready";
  const isInputDisabled = !isReady || isStreaming;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, blocks]);

  useEffect(() => {
    if (!user) return;
    apiFetch<SessionDetail>(`/sessions/${params.id}`)
      .then((data) => { setSession(data.session); setMessages(data.messages); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user, params.id]);

  const sessionId = session?.id;
  const wsConnected = useRef(false);
  useEffect(() => {
    if (!sessionId || !user) return;
    if (wsConnected.current) return;
    wsConnected.current = true;

    setConnStatus("connecting");
    setStatusMessage(null);

    let cancelled = false;

    createSessionWebSocket(
      sessionId,
      (msg: WSMessage) => {
        if (cancelled) return;
        switch (msg.type) {
          case "status":
            setConnStatus(msg.status);
            setStatusMessage(msg.message || null);
            if (msg.status === "disconnected") {
              // Connection lost — discard in-flight streaming state and reload
              // messages from DB so any partially/fully saved response appears.
              resetBlocks();
              setIsStreaming(false);
              apiFetch<SessionDetail>(`/sessions/${params.id}`)
                .then((data) => { if (!cancelled) setMessages(data.messages); })
                .catch(() => {});
            }
            break;
          case "user_message":
            setMessages((prev) => [...prev, {
              id: crypto.randomUUID(), session_id: sessionId, sender_type: "user",
              sender_id: msg.sender_id, content: msg.content, metadata: {}, created_at: new Date().toISOString(),
            }]);
            break;
          case "thinking":
          case "chunk":
          case "tool_use":
          case "tool_result":
          case "tool_progress":

            handleStreamMsg(msg);
            break;
          case "done": {
            finalize();
            const finalContent = flattenText();
            const savedBlocks = getBlocksMeta();
            const metadata: Record<string, unknown> = savedBlocks.length > 0 ? { blocks: savedBlocks } : {};
            resetBlocks();
            if (finalContent || savedBlocks.length > 0) {
              setMessages((msgs) => {
                if (msgs.some((m) => m.id === msg.messageId)) return msgs;
                return [...msgs, {
                  id: msg.messageId, session_id: sessionId, sender_type: "agent",
                  content: finalContent, metadata, created_at: new Date().toISOString(),
                }];
              });
            }
            setIsStreaming(false);

            break;
          }
          case "error":
            resetBlocks();
            setIsStreaming(false);

            setMessages((msgs) => [...msgs, {
              id: crypto.randomUUID(), session_id: sessionId, sender_type: "agent",
              content: `Error: ${msg.message}`, metadata: {}, created_at: new Date().toISOString(),
            }]);
            break;
          case "replay_start":
            setIsStreaming(true);


            resetBlocks();
            break;
          case "replay_end":
            break;
          case "cancelled": {
            finalize();
            const partialContent = flattenText();
            const partialBlocks = getBlocksMeta();
            const cancelMeta: Record<string, unknown> = partialBlocks.length > 0 ? { blocks: partialBlocks } : {};
            resetBlocks();
            if (partialContent || partialBlocks.length > 0) {
              const cancelledId = msg.messageId || crypto.randomUUID();
              setMessages((msgs) => {
                if (msgs.some((m) => m.id === cancelledId)) return msgs;
                return [...msgs, {
                  id: cancelledId, session_id: sessionId, sender_type: "agent",
                  content: partialContent,
                  metadata: cancelMeta, created_at: new Date().toISOString(),
                }];
              });
            }
            setIsStreaming(false);

            break;
          }
          case "stream_complete":
            setMessages((msgs) => {
              if (msgs.some((m) => m.id === msg.messageId)) return msgs;
              return [...msgs, {
                id: msg.messageId, session_id: sessionId, sender_type: "agent",
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
  }, [sessionId, user]);

  const handleSend = useCallback(
    (content: string) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !isReady) return;
      wsRef.current.send(JSON.stringify({ type: "message", content }));

      if (!session!.title) {
        const firstLine = content.trim().split("\n")[0];
        const autoTitle = firstLine.length > 60 ? firstLine.slice(0, 57) + "..." : firstLine;
        setSession((prev) => prev ? { ...prev, title: autoTitle } : prev);
        updateSidebarTitle(session!.id, autoTitle);
      }
    },
    [session, user, isReady, updateSidebarTitle]
  );

  const handleTitleClick = useCallback(() => {
    if (!session) return;
    setEditingTitle(session.title || "");
    setIsEditingTitle(true);
    setTimeout(() => titleInputRef.current?.focus(), 0);
  }, [session]);

  const handleTitleSave = useCallback(async () => {
    if (!session) return;
    setIsEditingTitle(false);
    const trimmed = editingTitle.trim();
    if (!trimmed || trimmed === session.title) return;
    setSession((prev) => prev ? { ...prev, title: trimmed } : prev);
    updateSidebarTitle(session.id, trimmed);
    try {
      await apiFetch(`/sessions/${session.id}/title`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed }),
      });
    } catch {
      setSession((prev) => prev ? { ...prev, title: session.title } : prev);
      updateSidebarTitle(session.id, session.title || "");
    }
  }, [session, editingTitle, updateSidebarTitle]);

  const handleTitleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.currentTarget.blur();
    } else if (e.key === "Escape") {
      setIsEditingTitle(false);
    }
  }, []);

  const handleCancel = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "cancel" }));
  }, []);

  const handleCapture = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;

    // Open a new window with just the chat content and trigger print (Save as PDF)
    const win = window.open("", "_blank");
    if (!win) return;

    // Collect all stylesheets from the current page
    const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
      .map((node) => node.outerHTML)
      .join("\n");

    win.document.write(`<!DOCTYPE html><html><head>${styles}
      <style>
        body { background: #09090b; margin: 0; padding: 24px; }
        @media print {
          body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        }
      </style>
    </head><body>${el.innerHTML}</body></html>`);
    win.document.close();

    // Let styles settle, then trigger print
    setTimeout(() => { win.print(); }, 500);
  }, []);

  const handleExportText = useCallback(() => {
    if (messages.length === 0) return;

    type Block = Record<string, unknown>;

    function renderToolTree(tools: Block[], indent: number): string {
      return tools.map((t) => {
        const parts: string[] = [];
        const name = t.name ?? "unknown";
        const err = t.is_error ? " [ERROR]" : "";
        parts.push(`<div class="tool-block" style="margin-left:${indent * 12}px">`);
        parts.push(`<strong>Tool: ${name}</strong>${err}`);
        const input = t.input as Record<string, unknown> | undefined;
        if (input && Object.keys(input).length > 0) {
          parts.push(`<pre>${JSON.stringify(input, null, 2)}</pre>`);
        }
        if (t.result != null) {
          const result = String(t.result);
          const short = result.length > 2000 ? result.slice(0, 2000) + "\n..." : result;
          parts.push(`<pre>${short.replace(/</g, "&lt;")}</pre>`);
        }
        const children = t.children as Block[] | undefined;
        if (children && children.length > 0) {
          parts.push(renderToolTree(children, indent + 1));
        }
        parts.push("</div>");
        return parts.join("\n");
      }).join("\n");
    }

    function renderBlocks(blocks: Block[]): string {
      // Build tree from flat blocks (same logic as message-bubble)
      const toolMap = new Map<string, Block & { children: Block[] }>();
      const roots: Block[] = [];
      for (const b of blocks) {
        if (b.type === "tool_call") {
          const node = { ...b, children: [] as Block[] };
          toolMap.set(String(b.tool_use_id ?? b.id ?? ""), node);
          if (b.parent_tool_use_id) {
            const parent = toolMap.get(String(b.parent_tool_use_id));
            if (parent) { parent.children.push(node); continue; }
          }
          roots.push(node);
        } else {
          roots.push(b);
        }
      }

      return roots.map((b) => {
        if (b.type === "thinking") {
          const text = String(b.content ?? "").slice(0, 300);
          const ellipsis = String(b.content ?? "").length > 300 ? "..." : "";
          return `<div class="thinking">Thinking: ${text}${ellipsis}</div>`;
        }
        if (b.type === "tool_call") return renderToolTree([b], 0);
        return String(b.content ?? "");
      }).join("\n\n");
    }

    const lines = messages.map((msg) => {
      const role = msg.sender_type === "user" ? "User" : "Agent";
      const header = `### ${role}\n`;
      const blocks = msg.metadata?.blocks as Block[] | undefined;
      const body = blocks && blocks.length > 0 ? renderBlocks(blocks) : msg.content;
      return header + "\n" + body;
    }).join("\n\n---\n\n");

    const title = session?.title || "Chat Export";
    const md = `# ${title}\n\n${lines}`;

    const win = window.open("", "_blank");
    if (!win) return;

    win.document.write(`<!DOCTYPE html><html><head>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.5; color: #222; font-size: 12px; }
        h1 { border-bottom: 2px solid #eee; padding-bottom: 6px; font-size: 18px; }
        h3 { margin-bottom: 2px; font-size: 13px; }
        hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
        p { margin: 4px 0; }
        code { background: #f4f4f4; padding: 1px 3px; border-radius: 3px; font-size: 0.85em; }
        pre { background: #f4f4f4; padding: 8px; border-radius: 4px; font-size: 10px; line-height: 1.4; white-space: pre-wrap; word-break: break-all; }
        strong { font-weight: 600; }
        .thinking { background: #f9f9f0; border-left: 3px solid #d4c87a; padding: 4px 8px; margin: 4px 0; font-size: 10px; color: #666; line-height: 1.4; white-space: pre-wrap; }
        .tool-block { font-size: 10px; color: #555; margin: 2px 0; }
        .tool-block pre { font-size: 9px; margin: 2px 0; padding: 4px 6px; }
        @media print {
          body { margin: 10px; }
        }
      </style>
    </head><body></body></html>`);
    win.document.close();

    win.document.body.innerHTML = marked.parse(md) as string;
    setTimeout(() => { win.print(); }, 500);
  }, [messages, session]);

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

  // Use visibleStatus for all UI rendering (debounced intermediate states)
  const displayStatus = visibleStatus ?? "ready";
  const statusStyle = STATUS_STYLES[displayStatus];
  const showConnecting = !isReady && visibleStatus !== null && !IMMEDIATE_STATUSES.has(displayStatus);

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
            {isEditingTitle ? (
              <input
                ref={titleInputRef}
                className="text-sm font-semibold text-foreground bg-transparent border-b border-primary outline-none w-[500px] max-w-[60vw]"
                value={editingTitle}
                onChange={(e) => setEditingTitle(e.target.value)}
                onBlur={handleTitleSave}
                onKeyDown={handleTitleKeyDown}
                maxLength={200}
              />
            ) : (
              <button
                className="group flex items-center gap-1.5 text-sm font-semibold text-foreground hover:text-foreground/70 transition-colors"
                onClick={handleTitleClick}
              >
                <span>{session.title || "New Session"}</span>
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-muted-foreground/40 group-hover:text-muted-foreground transition-colors"
                >
                  <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                  <path d="m15 5 4 4" />
                </svg>
              </button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleCapture}
              disabled={messages.length === 0}
              className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors disabled:opacity-30 disabled:pointer-events-none"
              title="Print chat"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            </button>
            <button
              onClick={handleExportText}
              disabled={messages.length === 0}
              className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors disabled:opacity-30 disabled:pointer-events-none"
              title="Export chat as text"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            </button>
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full transition-colors duration-300 ${statusStyle.dot}`} />
              <span className={`text-xs font-medium transition-colors duration-300 ${statusStyle.text}`}>{STATUS_LABELS[displayStatus]}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Status banners — only shown after debounce delay for intermediate states */}
      {showConnecting && (
        <div className="shrink-0 border-b border-warning/10 bg-warning/5 px-6 py-2.5 animate-fade-in">
          <div className="mx-auto flex max-w-4xl items-center justify-center gap-2">
            <svg className="h-4 w-4 animate-spin text-warning" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            <span className="text-xs text-warning">{STATUS_LABELS[displayStatus]}{statusMessage && ` — ${statusMessage}`}</span>
          </div>
        </div>
      )}
      {displayStatus === "offline" && (
        <div className="shrink-0 border-b border-destructive/10 bg-destructive/5 px-6 py-2.5">
          <div className="mx-auto flex max-w-4xl items-center justify-center gap-2">
            <span className="text-xs text-destructive">Agent is offline{statusMessage && ` — ${statusMessage}`}</span>
          </div>
        </div>
      )}
      {displayStatus === "disconnected" && (
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

            {(blocks.length > 0 || isStreaming) && (
              <StreamingResponse blocks={blocks} isStreaming={isStreaming} />
            )}
          </div>
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-border/30 px-6 py-4">
        <div className="mx-auto max-w-4xl space-y-2">
          {todos.length > 0 && <TodoPanel todos={todos} />}
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
