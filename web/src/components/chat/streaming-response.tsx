"use client";

import { memo } from "react";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { ToolCallCard } from "@/components/chat/tool-call-card";
import type { StreamBlock } from "@/types";

interface StreamingResponseProps {
  blocks: StreamBlock[];
  isStreaming: boolean;
}

const TextBlockView = memo(function TextBlockView({
  content,
  isLast,
  isStreaming,
}: {
  content: string;
  isLast: boolean;
  isStreaming: boolean;
}) {
  return (
    <div className="markdown-body break-words text-[14px] leading-[1.7] text-chat-agent-fg">
      <MarkdownContent content={content} />
      {isLast && isStreaming && (
        <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse-soft bg-primary" />
      )}
    </div>
  );
});

export const StreamingResponse = memo(function StreamingResponse({
  blocks,
  isStreaming,
}: StreamingResponseProps) {
  const hasContent = blocks.length > 0;

  return (
    <div className="flex gap-3 animate-fade-in">
      {/* Avatar */}
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-xs font-semibold text-muted-foreground">
        AI
      </div>

      {/* Content */}
      <div className="min-w-0 max-w-[75%] space-y-2">
        {/* Blocks */}
        {blocks.map((block, idx) => {
          const isLast = idx === blocks.length - 1;

          if (block.type === "text") {
            return (
              <div
                key={block.id}
                className="rounded-2xl rounded-tl-md bg-chat-agent px-4 py-3"
              >
                <TextBlockView
                  content={block.content}
                  isLast={isLast}
                  isStreaming={isStreaming}
                />
              </div>
            );
          }

          if (block.type === "tool_call") {
            return <ToolCallCard key={block.id} block={block} />;
          }

          return null;
        })}

        {/* Loading indicator: visible while streaming and last block is not actively receiving text */}
        {isStreaming && (blocks.length === 0 || blocks[blocks.length - 1]?.type !== "text") && (
          <div className="rounded-2xl rounded-tl-md bg-chat-agent px-4 py-3">
            <div className="flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-muted-foreground/50"
                style={{ animationDelay: "0ms" }}
              />
              <span
                className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-muted-foreground/50"
                style={{ animationDelay: "200ms" }}
              />
              <span
                className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-muted-foreground/50"
                style={{ animationDelay: "400ms" }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
});
