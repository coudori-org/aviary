import type { StreamBlock } from "@/types";
import { buildBlockTree } from "./build-block-tree";

/**
 * Restore saved block metadata into a StreamBlock tree.
 *
 * Pass `messageId` so generated text/thinking ids are namespaced
 * (`{msgId}-text-0`, ...) and globally unique — chat search uses these
 * as DOM lookup keys. Tool blocks use the DB-unique `tool_use_id`.
 */
export function restoreBlocks(
  raw: Array<Record<string, unknown>>,
  cancelled = false,
  messageId?: string,
): StreamBlock[] {
  const prefix = messageId ? `${messageId}-` : "";
  const flat: StreamBlock[] = raw.map((block, i) => {
    if (block.type === "tool_call") {
      if (typeof block.tool_use_id !== "string" || typeof block.name !== "string") {
        throw new Error(
          `restoreBlocks: tool_call block missing required tool_use_id or name (index ${i})`,
        );
      }
      const hasResult = block.result != null;
      return {
        type: "tool_call" as const,
        id: block.tool_use_id,
        name: block.name,
        input: (block.input as Record<string, unknown>) ?? {},
        status: "complete" as const,
        result: hasResult
          ? String(block.result)
          : cancelled
            ? "[Cancelled]"
            : undefined,
        is_error:
          block.is_error === true
            ? true
            : !hasResult && cancelled
              ? true
              : undefined,
        parent_tool_use_id:
          typeof block.parent_tool_use_id === "string" ? block.parent_tool_use_id : undefined,
      };
    }
    if (block.type === "thinking") {
      return {
        type: "thinking" as const,
        id: `${prefix}thinking-${i}`,
        content: String(block.content ?? ""),
      };
    }
    return {
      type: "text" as const,
      id: `${prefix}text-${i}`,
      content: String(block.content ?? ""),
    };
  });

  return buildBlockTree(flat);
}
