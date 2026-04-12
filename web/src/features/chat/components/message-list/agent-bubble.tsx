"use client";

import { useMemo } from "react";
import { restoreBlocks } from "@/features/chat/lib/restore-blocks";
import { groupConsecutiveToolCalls } from "@/features/chat/lib/group-blocks";
import { MarkdownContent } from "@/features/chat/components/markdown/markdown-content";
import { ToolCallCard } from "@/features/chat/components/blocks/tool-call-card";
import { ToolGroupChip } from "@/features/chat/components/blocks/tool-group-chip";
import { ThinkingChip } from "@/features/chat/components/blocks/thinking-chip";
import { MessageCopyButton } from "./message-copy-button";
import { useChatSearchTargetId } from "@/features/chat/hooks/chat-search-context";
import { cn } from "@/lib/utils";
import type { Message } from "@/types";

interface AgentBubbleProps {
  message: Message;
  /** When false, render an invisible spacer in the avatar slot so the
   *  bubble stays horizontally aligned with the run's first message. */
  showAvatar?: boolean;
}

/**
 * AgentBubble — historical agent message.
 *
 * Block restoration pipeline:
 *   1. `restoreBlocks` rebuilds the StreamBlock tree from saved metadata
 *      (re-attaches sub-agent children to their parents)
 *   2. `groupConsecutiveToolCalls` clusters runs of leaf tool calls into
 *      collapsible groups so historical messages don't render as walls
 *   3. View renders text / thinking / tool / tool-group inline
 *
 * Falls back to plain markdown for legacy messages without saved blocks.
 *
 * Width is constrained to 88% (vs 60% for user) — agent messages are
 * usually long, structured, and contain code blocks / tool cards that
 * benefit from horizontal room.
 */
export function AgentBubble({ message, showAvatar = true }: AgentBubbleProps) {
  const savedBlocks = message.metadata?.blocks as Array<Record<string, unknown>> | undefined;
  const hasBlocks = Array.isArray(savedBlocks) && savedBlocks.length > 0;
  const isCancelled = message.metadata?.cancelled === true;
  const isError = message.metadata?.error === true;
  const activeTargetId = useChatSearchTargetId();

  const items = useMemo(() => {
    if (!hasBlocks) return [];
    const restored = restoreBlocks(savedBlocks!, isCancelled, message.id);
    return groupConsecutiveToolCalls(restored);
  }, [hasBlocks, savedBlocks, isCancelled, message.id]);

  const textBubbleClass = (targetId: string) =>
    cn(
      "rounded-xl rounded-tl-sm bg-elevated shadow-2 px-4 py-3 transition-shadow",
      activeTargetId === targetId &&
        "ring-2 ring-info/60 ring-offset-2 ring-offset-canvas",
    );

  return (
    <div className="flex gap-3 group animate-fade-in">
      {showAvatar ? (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-raised type-small text-fg-muted">
          AI
        </div>
      ) : (
        <div className="h-8 w-8 shrink-0" aria-hidden="true" />
      )}

      <div className="min-w-0 max-w-[80%] space-y-1.5">
        {isError ? (
          <div className="rounded-xl rounded-tl-sm border border-danger/20 bg-danger/[0.06] px-4 py-3">
            <p className="type-body text-danger">{message.content}</p>
          </div>
        ) : hasBlocks ? (
          items.map((item) => {
            if (item.kind === "tool-group") {
              return (
                <ToolGroupChip key={`group-${item.tools[0].id}`} tools={item.tools} />
              );
            }
            const block = item.block;
            if (block.type === "tool_call") {
              return <ToolCallCard key={block.id} block={block} />;
            }
            if (block.type === "thinking") {
              return <ThinkingChip key={block.id} targetId={block.id} content={block.content} />;
            }
            return (
              <div
                key={block.id}
                data-search-target={block.id}
                className={textBubbleClass(block.id)}
              >
                <div className="markdown-body break-words type-body text-fg-secondary">
                  <MarkdownContent content={block.content} />
                </div>
              </div>
            );
          })
        ) : (
          <div
            data-search-target={`${message.id}/body`}
            className={textBubbleClass(`${message.id}/body`)}
          >
            <div className="markdown-body break-words type-body text-fg-secondary">
              <MarkdownContent content={message.content} />
            </div>
          </div>
        )}

        {isCancelled && (
          <div className="rounded-md border border-warning/20 bg-warning/[0.04] px-3 py-1.5 type-caption text-warning">
            Cancelled by user
          </div>
        )}

        <div className="opacity-0 transition-opacity group-hover:opacity-100">
          <MessageCopyButton text={message.content} />
        </div>
      </div>
    </div>
  );
}
