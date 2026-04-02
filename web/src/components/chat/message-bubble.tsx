"use client";

import { useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { ToolCallCard } from "@/components/chat/tool-call-card";
import { buildTree } from "@/components/chat/use-streaming-blocks";
import type { Message, StreamBlock, ToolCallBlock } from "@/types";

interface MessageBubbleProps {
  message: Message;
  currentUserId?: string;
}

function MessageCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="mt-1 flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] text-muted-foreground/60 transition-colors hover:text-muted-foreground"
      title="Copy message"
    >
      {copied ? (
        <>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          Copied
        </>
      ) : (
        <>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          Copy
        </>
      )}
    </button>
  );
}

/** Convert raw saved block metadata into a StreamBlock tree */
function restoreBlocks(raw: Array<Record<string, unknown>>): StreamBlock[] {
  const flat: StreamBlock[] = raw.map((block, i) => {
    if (block.type === "tool_call") {
      return {
        type: "tool_call" as const,
        id: String(block.tool_use_id ?? `saved-${i}`),
        name: String(block.name ?? "unknown"),
        input: (block.input as Record<string, unknown>) ?? {},
        status: "complete" as const,
        result: block.result != null ? String(block.result) : undefined,
        is_error: block.is_error === true ? true : undefined,
        parent_tool_use_id: block.parent_tool_use_id ? String(block.parent_tool_use_id) : undefined,
      };
    }
    return {
      type: "text" as const,
      id: `text-${i}`,
      content: String(block.content ?? ""),
    };
  });
  return buildTree(flat);
}

export function MessageBubble({ message, currentUserId }: MessageBubbleProps) {
  const isUser = message.sender_type === "user";
  const savedBlocks = !isUser ? (message.metadata?.blocks as Array<Record<string, unknown>> | undefined) : undefined;
  const hasBlocks = Array.isArray(savedBlocks) && savedBlocks.length > 0;

  return (
    <div
      className={cn(
        "group flex gap-3 animate-fade-in",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-semibold",
          isUser
            ? "bg-chat-user/20 text-chat-user-fg"
            : "bg-secondary text-muted-foreground"
        )}
      >
        {isUser ? "You" : "AI"}
      </div>

      {/* Message content */}
      <div className={cn("max-w-[75%] space-y-1.5", isUser ? "items-end" : "items-start")}>
        {isUser ? (
          <div className="rounded-2xl rounded-tr-md bg-chat-user px-4 py-3 text-[14px] leading-[1.7] text-chat-user-fg">
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          </div>
        ) : hasBlocks ? (
          /* Render saved blocks as tree (subagent tools nested under Agent) */
          <>
            {restoreBlocks(savedBlocks!).map((block) => {
              if (block.type === "tool_call") {
                return <ToolCallCard key={block.id} block={block} />;
              }
              return (
                <div key={block.id} className="rounded-2xl rounded-tl-md bg-chat-agent px-4 py-3 text-[14px] leading-[1.7] text-chat-agent-fg">
                  <div className="markdown-body break-words">
                    <MarkdownContent content={block.content} />
                  </div>
                </div>
              );
            })}
          </>
        ) : (
          /* Fallback: plain text (old messages without blocks metadata) */
          <div className="rounded-2xl rounded-tl-md bg-chat-agent px-4 py-3 text-[14px] leading-[1.7] text-chat-agent-fg">
            <div className="markdown-body break-words">
              <MarkdownContent content={message.content} />
            </div>
          </div>
        )}

        {/* Copy button (visible on hover) */}
        {!isUser && (
          <div className="opacity-0 transition-opacity group-hover:opacity-100">
            <MessageCopyButton text={message.content} />
          </div>
        )}
      </div>
    </div>
  );
}
