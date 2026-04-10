import type { StreamBlock, ToolCallBlock } from "@/types";

/** True if the (lowercased) query appears in this tool call's name,
 *  input, result, or any nested sub-agent child. */
export function toolCallMatches(block: ToolCallBlock, query: string): boolean {
  if (!query) return false;
  if (block.name.toLowerCase().includes(query)) return true;
  try {
    if (JSON.stringify(block.input).toLowerCase().includes(query)) return true;
  } catch {
    // Non-serializable input — skip.
  }
  if (block.result?.toLowerCase().includes(query)) return true;
  return block.children ? anyBlockMatches(block.children, query) : false;
}

function anyBlockMatches(blocks: StreamBlock[], query: string): boolean {
  for (const block of blocks) {
    if (block.type === "text" || block.type === "thinking") {
      if (block.content.toLowerCase().includes(query)) return true;
    } else if (block.type === "tool_call") {
      if (toolCallMatches(block, query)) return true;
    }
  }
  return false;
}
