import type { StreamBlock, ToolCallBlock } from "@/types";

/**
 * Cluster runs of consecutive `tool_call` blocks (≥ threshold) into a single
 * collapsible group render item. Pure function.
 */

export interface RenderItemBlock {
  kind: "block";
  block: StreamBlock;
}

export interface RenderItemToolGroup {
  kind: "tool-group";
  tools: ToolCallBlock[];
}

export type RenderItem = RenderItemBlock | RenderItemToolGroup;

const DEFAULT_GROUP_THRESHOLD = 3;

export function groupConsecutiveToolCalls(
  blocks: StreamBlock[],
  threshold: number = DEFAULT_GROUP_THRESHOLD,
): RenderItem[] {
  const result: RenderItem[] = [];
  let pending: ToolCallBlock[] = [];

  const flush = () => {
    if (pending.length === 0) return;
    if (pending.length >= threshold) {
      result.push({ kind: "tool-group", tools: pending });
    } else {
      for (const tool of pending) {
        result.push({ kind: "block", block: tool });
      }
    }
    pending = [];
  };

  for (const block of blocks) {
    if (block.type === "tool_call") {
      pending.push(block);
    } else {
      flush();
      result.push({ kind: "block", block });
    }
  }
  flush();

  return result;
}
