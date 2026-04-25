"use client";

import { useMemo } from "react";
import { restoreBlocks } from "@/features/chat/lib/restore-blocks";
import { groupConsecutiveToolCalls } from "@/features/chat/lib/group-blocks";
import { MarkdownContent } from "@/features/chat/components/markdown/markdown-content";
import { ToolCallCard } from "@/features/chat/components/blocks/tool-call-card";
import { ToolGroupChip } from "@/features/chat/components/blocks/tool-group-chip";
import { ThinkingChip } from "@/features/chat/components/blocks/thinking-chip";
import { ErrorBlockView } from "@/features/chat/components/blocks/error-block";
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
      "rounded-xl rounded-tl-sm bg-raised border border-border-subtle shadow-sm px-4 py-3 transition-shadow",
      activeTargetId === targetId &&
        "ring-2 ring-accent/60 ring-offset-2 ring-offset-canvas",
    );

  return (
    <div className="flex gap-3 group animate-fade-in">
      {showAvatar ? (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent-soft border border-accent/30 type-small text-accent">
          AI
        </div>
      ) : (
        <div className="h-8 w-8 shrink-0" aria-hidden="true" />
      )}

      <div className="min-w-0 max-w-[80%] space-y-1.5">
        {hasBlocks ? (
          // hasBlocks first: persisted error messages also carry blocks,
          // with the error block at the tail.
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
            if (block.type === "error") {
              return <ErrorBlockView key={block.id} targetId={block.id} message={block.message} />;
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
        ) : isError ? (
          <div className="rounded-xl rounded-tl-sm border border-status-error/30 bg-status-error-soft/40 px-4 py-3">
            <p className="type-body text-status-error">{message.content}</p>
          </div>
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
          <div className="rounded-md border border-status-warn/30 bg-status-warn-soft/40 px-3 py-1.5 type-caption text-status-warn">
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
