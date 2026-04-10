"use client";

import { forwardRef, Fragment } from "react";
import { MessageBubble } from "./message-bubble";
import { TimeDivider } from "./time-divider";
import { StreamingResponse } from "@/features/chat/components/blocks/streaming-response";
import { ChatEmptyState } from "@/features/chat/components/chat-empty-state";
import { computeTimeDividerLabel } from "@/features/chat/lib/relative-time";
import type { Message, StreamBlock } from "@/types";

interface MessageListProps {
  messages: Message[];
  blocks: StreamBlock[];
  isStreaming: boolean;
  isReady: boolean;
}

/**
 * MessageList — scrollable message container with empty state and live
 * streaming response.
 *
 * Inserts a `TimeDivider` between consecutive messages when the gap
 * exceeds 10 minutes (or when the conversation crosses a calendar day).
 * The label logic lives in `computeTimeDividerLabel` so this component
 * stays a thin orchestrator.
 *
 * Forward-refs the scroll element so the parent can attach
 * scroll-to-bottom and chat export hooks.
 */
export const MessageList = forwardRef<HTMLDivElement, MessageListProps>(
  function MessageList({ messages, blocks, isStreaming, isReady }, ref) {
    return (
      <div ref={ref} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-container-prose px-6 py-6">
          {messages.length === 0 && isReady && !isStreaming && <ChatEmptyState />}

          <div className="space-y-5">
            {messages.map((msg, idx) => {
              const prev = idx > 0 ? messages[idx - 1] : null;
              const dividerLabel = prev
                ? computeTimeDividerLabel(prev.created_at, msg.created_at)
                : null;

              return (
                <Fragment key={msg.id}>
                  {dividerLabel && <TimeDivider label={dividerLabel} />}
                  <MessageBubble message={msg} />
                </Fragment>
              );
            })}

            {(blocks.length > 0 || isStreaming) && (
              <StreamingResponse blocks={blocks} isStreaming={isStreaming} />
            )}
          </div>
        </div>
      </div>
    );
  },
);
