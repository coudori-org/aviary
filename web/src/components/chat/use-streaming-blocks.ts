"use client";

import { useCallback, useRef, useState } from "react";
import type { StreamBlock, TextBlock, ToolCallBlock, TodoItem } from "@/types";
import type { WSMessage } from "@/lib/websocket";

/**
 * Convert a flat list of blocks into a tree where subagent tool calls are
 * nested inside their parent Agent tool call's `children` array.
 */
function buildTree(flat: StreamBlock[]): StreamBlock[] {
  const toolMap = new Map<string, ToolCallBlock>();
  const tree: StreamBlock[] = [];

  // First pass: create cloned tool blocks with empty children
  for (const b of flat) {
    if (b.type === "tool_call") {
      toolMap.set(b.id, { ...b, children: [] });
    }
  }

  // Second pass: attach children or push to top-level
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

  // Strip empty children arrays
  for (const node of toolMap.values()) {
    if (node.children && node.children.length === 0) {
      delete node.children;
    }
  }

  return tree;
}

export function useStreamingBlocks() {
  const [blocks, setBlocks] = useState<StreamBlock[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const blocksRef = useRef<StreamBlock[]>([]);
  const rafRef = useRef<number>(0);

  const scheduleRender = useCallback(() => {
    if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(() => {
        setBlocks(buildTree(blocksRef.current));
        rafRef.current = 0;
      });
    }
  }, []);

  const updateBlocks = useCallback(
    (fn: (blocks: StreamBlock[]) => StreamBlock[]) => {
      blocksRef.current = fn(blocksRef.current);
      scheduleRender();
    },
    [scheduleRender],
  );

  const handleMessage = useCallback(
    (msg: WSMessage) => {
      switch (msg.type) {
        case "chunk": {
          updateBlocks((prev) => {
            // When new text arrives after tool calls, mark all running tools as complete
            // (the model can only respond after tools finish).
            const resolved = prev.map((b) =>
              b.type === "tool_call" && b.status === "running"
                ? { ...b, status: "complete" as const }
                : b,
            );
            const last = resolved[resolved.length - 1];
            if (last?.type === "text") {
              const updated: TextBlock = { ...last, content: last.content + msg.content };
              return [...resolved.slice(0, -1), updated];
            }
            const id = `text-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
            return [...resolved, { type: "text", id, content: msg.content }];
          });
          break;
        }

        case "tool_use": {
          const toolBlock: ToolCallBlock = {
            type: "tool_call",
            id: msg.tool_use_id || `tool-${Date.now()}`,
            name: msg.name,
            input: msg.input,
            status: "running",
            ...(msg.parent_tool_use_id ? { parent_tool_use_id: msg.parent_tool_use_id } : {}),
          };
          updateBlocks((prev) => [...prev, toolBlock]);

          // Detect TodoWrite → update todo panel
          if (msg.name === "TodoWrite" && Array.isArray(msg.input?.todos)) {
            const items = (msg.input.todos as Array<Record<string, string>>).map(
              (t) => ({
                content: t.content ?? "",
                status: (t.status ?? "pending") as TodoItem["status"],
              }),
            );
            setTodos(items);
          }
          break;
        }

        case "tool_result": {
          updateBlocks((prev) =>
            prev.map((b) =>
              b.type === "tool_call" && b.id === msg.tool_use_id
                ? { ...b, status: "complete" as const, result: msg.content, is_error: msg.is_error }
                : b,
            ),
          );
          break;
        }

        case "tool_progress": {
          updateBlocks((prev) =>
            prev.map((b) =>
              b.type === "tool_call" && b.id === msg.tool_use_id
                ? { ...b, elapsed: msg.elapsed_time_seconds }
                : b,
            ),
          );
          break;
        }
      }
    },
    [updateBlocks],
  );

  const reset = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    }
    blocksRef.current = [];
    setBlocks([]);
    setTodos([]);
  }, []);

  /** Mark any remaining running tools as complete (called before extracting final state) */
  const finalize = useCallback(() => {
    blocksRef.current = blocksRef.current.map((b) =>
      b.type === "tool_call" && b.status === "running"
        ? { ...b, status: "complete" as const }
        : b,
    );
  }, []);

  const flattenText = useCallback((): string => {
    return blocksRef.current
      .filter((b): b is TextBlock => b.type === "text")
      .map((b) => b.content)
      .join("");
  }, []);

  /** Serialize all blocks for saving in message metadata (flat, preserves order) */
  const getBlocksMeta = useCallback((): Record<string, unknown>[] => {
    return blocksRef.current.map((b) => {
      if (b.type === "text") {
        return { type: "text", content: b.content };
      }
      return {
        type: "tool_call",
        name: b.name,
        input: b.input,
        tool_use_id: b.id,
        result: b.result,
        ...(b.is_error ? { is_error: true } : {}),
        ...(b.parent_tool_use_id ? { parent_tool_use_id: b.parent_tool_use_id } : {}),
      };
    });
  }, []);

  return { blocks, todos, handleMessage, reset, flattenText, getBlocksMeta, finalize };
}

/** Re-export buildTree for use by message-bubble (past messages) */
export { buildTree };
