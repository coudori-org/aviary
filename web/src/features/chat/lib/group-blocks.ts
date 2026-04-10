import type { StreamBlock, ToolCallBlock } from "@/types";

/**
 * Render-time grouping of consecutive tool calls into collapsible bundles.
 *
 * The streaming pipeline produces a flat list of blocks (after tree-building
 * for sub-agent nesting). Long sessions accumulate dozens of leaf tool calls
 * with no text between them, which becomes a vertical wall in the UI.
 *
 * `groupConsecutiveToolCalls` walks the block list and clusters runs of
 * tool_call blocks (≥ `threshold`) into a `ToolGroup` render item that the
 * view layer renders as a single collapsible header. Anything below the
 * threshold passes through unchanged so pairs and singletons stay visible.
 *
 * Pure function — no React, no state, fully testable.
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
      // Below threshold — emit individually so pairs/singletons render normally
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
