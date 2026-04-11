"use client";

import { memo, useMemo } from "react";
import { TextBlockView } from "./text-block";
import { ThinkingChip } from "./thinking-chip";
import { ToolCallCard } from "./tool-call-card";
import { ToolGroupChip } from "./tool-group-chip";
import { ActivityIndicator } from "./activity-indicator";
import { groupConsecutiveToolCalls } from "@/features/chat/lib/group-blocks";
import type { StreamBlock } from "@/types";

interface StreamingResponseProps {
  blocks: StreamBlock[];
  isStreaming: boolean;
}

/**
 * StreamingResponse — renders the live agent message-in-progress. Consecutive
 * tool calls are bundled into a collapsible group via `groupConsecutiveToolCalls`.
 */
export const StreamingResponse = memo(function StreamingResponse({
  blocks,
  isStreaming,
}: StreamingResponseProps) {
  const items = useMemo(() => groupConsecutiveToolCalls(blocks), [blocks]);

  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-raised type-small text-fg-muted">
        AI
      </div>

      <div className="min-w-0 max-w-[80%] space-y-2">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1;

          if (item.kind === "tool-group") {
            return <ToolGroupChip key={`group-${item.tools[0].id}`} tools={item.tools} />;
          }

          const block = item.block;

          if (block.type === "thinking") {
            return (
              <ThinkingChip
                key={block.id}
                content={block.content}
                isActive={isLast && isStreaming}
              />
            );
          }
          if (block.type === "text") {
            return <TextBlockView key={block.id} content={block.content} />;
          }
          if (block.type === "tool_call") {
            return <ToolCallCard key={block.id} block={block} />;
          }
          return null;
        })}

        {isStreaming && <ActivityIndicator />}
      </div>
    </div>
  );
});
