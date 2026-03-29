"use client";

import { cn } from "@/lib/utils";
import type { Message } from "@/types";

interface MessageBubbleProps {
  message: Message;
  currentUserId?: string;
}

export function MessageBubble({ message, currentUserId }: MessageBubbleProps) {
  const isUser = message.sender_type === "user";
  const isOwnMessage = isUser && message.sender_id === currentUserId;

  return (
    <div
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-2 text-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        )}
      >
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
        {message.metadata && Object.keys(message.metadata).length > 0 && message.metadata.tool_calls && (
          <div className="mt-2 space-y-1 border-t border-white/20 pt-2">
            {(message.metadata.tool_calls as any[]).map((tool: any, i: number) => (
              <div key={i} className="rounded bg-black/10 px-2 py-1 text-xs font-mono">
                {tool.name}({JSON.stringify(tool.input).slice(0, 100)})
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
