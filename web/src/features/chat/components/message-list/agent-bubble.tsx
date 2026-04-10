"use client";

import { useMemo } from "react";
import { restoreBlocks } from "@/features/chat/lib/restore-blocks";
import { groupConsecutiveToolCalls } from "@/features/chat/lib/group-blocks";
import { MarkdownContent } from "@/features/chat/components/markdown/markdown-content";
import { ToolCallCard } from "@/features/chat/components/blocks/tool-call-card";
import { ToolGroupChip } from "@/features/chat/components/blocks/tool-group-chip";
import { ThinkingChip } from "@/features/chat/components/blocks/thinking-chip";
import { MessageCopyButton } from "./message-copy-button";
import type { Message } from "@/types";

interface AgentBubbleProps {
  message: Message;
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
 */
export function AgentBubble({ message }: AgentBubbleProps) {
  const savedBlocks = message.metadata?.blocks as Array<Record<string, unknown>> | undefined;
  const hasBlocks = Array.isArray(savedBlocks) && savedBlocks.length > 0;
  const isCancelled = message.metadata?.cancelled === true;

  const items = useMemo(() => {
    if (!hasBlocks) return [];
    const restored = restoreBlocks(savedBlocks!, isCancelled);
    return groupConsecutiveToolCalls(restored);
  }, [hasBlocks, savedBlocks, isCancelled]);

  return (
    <div className="flex gap-3 group animate-fade-in">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-raised type-small text-fg-muted">
        AI
      </div>

      <div className="max-w-[75%] space-y-1.5">
        {hasBlocks ? (
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
              return <ThinkingChip key={block.id} content={block.content} />;
            }
            return (
              <div
                key={block.id}
                className="rounded-xl rounded-tl-sm bg-elevated shadow-2 px-4 py-3"
              >
                <div className="markdown-body break-words type-body text-fg-secondary">
                  <MarkdownContent content={block.content} />
                </div>
              </div>
            );
          })
        ) : (
          <div className="rounded-xl rounded-tl-sm bg-elevated shadow-2 px-4 py-3">
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
