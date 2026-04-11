import type { StreamBlock, ToolCallBlock } from "@/types";

/**
 * Convert a flat list of blocks into a tree where blocks with
 * `parent_tool_use_id` are nested inside their parent tool call's
 * `children` array. Only tool_call blocks use parent_tool_use_id
 * (sub-agent tool calls).
 *
 * Pure function — extracted from useStreamingBlocks so that it can be
 * unit-tested and reused by saved-message restoration.
 */
export function buildBlockTree(flat: StreamBlock[]): StreamBlock[] {
  const toolMap = new Map<string, ToolCallBlock>();
  const tree: StreamBlock[] = [];

  // First pass: clone tool blocks with empty children arrays
  for (const b of flat) {
    if (b.type === "tool_call") {
      toolMap.set(b.id, { ...b, children: [] });
    }
  }

  // Second pass: nest under parent or push to top level
  for (const b of flat) {
    if (b.type === "tool_call") {
      const node = toolMap.get(b.id)!;
      const parentId = b.parent_tool_use_id;
      if (parentId && toolMap.has(parentId)) {
        toolMap.get(parentId)!.children!.push(node);
      } else {
        tree.push(node);
      }
    } else {
      tree.push(b);
    }
  }

  // Strip empty children arrays for cleaner serialization
  for (const node of toolMap.values()) {
    if (node.children && node.children.length === 0) {
      delete node.children;
    }
  }

  return tree;
}
