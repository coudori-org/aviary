"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StreamBlock, TextBlock, ThinkingBlock, ToolCallBlock, TodoItem } from "@/types";
import type { WSMessage } from "@/lib/ws";
import { buildBlockTree } from "@/features/chat/lib/build-block-tree";

interface UseStreamingBlocksOptions {
  /** Fired once per tool_result with the completed tool's name. Consumers
   *  use this to detect filesystem-touching tools (Bash/Edit/Write/…) and
   *  nudge dependent UI (e.g. the workspace file tree) to refresh. */
  onToolCompleted?: (toolName: string) => void;
}

/**
 * useStreamingBlocks — accumulates streaming WS deltas into a structured
 * block list (text / thinking / tool_call), with tree assembly for sub-agent
 * tools, and surfaces extracted Todo items.
 *
 * Render scheduling uses requestAnimationFrame so a burst of high-frequency
 * deltas only triggers a single React re-render per frame.
 */
export function useStreamingBlocks(options: UseStreamingBlocksOptions = {}) {
  const [blocks, setBlocks] = useState<StreamBlock[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const blocksRef = useRef<StreamBlock[]>([]);
  const rafRef = useRef<number>(0);
  // Stable callback ref so handleMessage doesn't re-bind each render — the
  // WS subscription keys on handleMessage identity.
  const onToolCompletedRef = useRef(options.onToolCompleted);
  useEffect(() => {
    onToolCompletedRef.current = options.onToolCompleted;
  }, [options.onToolCompleted]);

  const scheduleRender = useCallback(() => {
    if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(() => {
        setBlocks(buildBlockTree(blocksRef.current));
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
        case "thinking":
          updateBlocks((prev) => {
            const last = prev[prev.length - 1];
            if (last?.type === "thinking") {
              const updated: ThinkingBlock = { ...last, content: last.content + msg.content };
              return [...prev.slice(0, -1), updated];
            }
            const id = `thinking-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
            return [...prev, { type: "thinking", id, content: msg.content }];
          });
          break;

        case "chunk":
          updateBlocks((prev) => {
            // When new text arrives after tool calls, mark all running tools as complete —
            // the model can only respond after tools finish.
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

          if (msg.name === "TodoWrite" && Array.isArray(msg.input?.todos)) {
            const items = (msg.input.todos as Array<Record<string, string>>).map((t) => ({
              content: t.content ?? "",
              status: (t.status ?? "pending") as TodoItem["status"],
            }));
            setTodos(items);
          }
          break;
        }

        case "tool_result": {
          let completedName: string | null = null;
          updateBlocks((prev) =>
            prev.map((b) => {
              if (b.type === "tool_call" && b.id === msg.tool_use_id) {
                completedName = b.name;
                return { ...b, status: "complete" as const, result: msg.content, is_error: msg.is_error };
              }
              return b;
            }),
          );
          if (completedName && onToolCompletedRef.current) {
            onToolCompletedRef.current(completedName);
          }
          break;
        }

        case "tool_progress":
          updateBlocks((prev) =>
            prev.map((b) =>
              b.type === "tool_call" && b.id === msg.tool_use_id
                ? { ...b, elapsed: msg.elapsed_time_seconds }
                : b,
            ),
          );
          break;
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

  /** Mark any remaining running tools as complete (called before extracting final state). */
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

  const getBlocksMeta = useCallback((): Record<string, unknown>[] => {
    return blocksRef.current
      .filter((b) => !((b.type === "text" || b.type === "thinking") && b.content.trim() === ""))
      .map((b) => {
        if (b.type === "text") return { type: "text", content: b.content };
        if (b.type === "thinking") return { type: "thinking", content: b.content };
        if (b.type === "error") return { type: "error", message: b.message };
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
