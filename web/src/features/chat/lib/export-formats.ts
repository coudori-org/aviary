/**
 * Export helpers — turn a list of messages into printable HTML.
 *
 * Tool blocks, thinking, and structural chrome are built as plain HTML
 * strings; only text content is passed through `mdToHtml` so markdown
 * syntax inside tool result <pre> blocks isn't reinterpreted.
 */

import type { StreamBlock, ToolCallBlock } from "@/types";
import { restoreBlocks } from "./restore-blocks";

const MAX_TOOL_RESULT_CHARS = 2000;

function escapeHtml(str: string): string {
  return str.replace(/[&<>"']/g, (c) => {
    switch (c) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      default:
        return "&#39;";
    }
  });
}

function renderToolHtml(tool: ToolCallBlock, indent: number): string {
  const parts: string[] = [];
  const err = tool.is_error ? " [ERROR]" : "";
  parts.push(`<div class="tool-block" style="margin-left:${indent * 12}px">`);
  parts.push(`<strong>Tool: ${escapeHtml(tool.name)}</strong>${err}`);

  if (Object.keys(tool.input).length > 0) {
    parts.push(`<pre>${escapeHtml(JSON.stringify(tool.input, null, 2))}</pre>`);
  }
  if (tool.result != null) {
    const short =
      tool.result.length > MAX_TOOL_RESULT_CHARS
        ? tool.result.slice(0, MAX_TOOL_RESULT_CHARS) + "\n..."
        : tool.result;
    parts.push(`<pre>${escapeHtml(short)}</pre>`);
  }
  if (tool.children) {
    for (const child of tool.children) {
      if (child.type === "tool_call") parts.push(renderToolHtml(child, indent + 1));
    }
  }
  parts.push("</div>");
  return parts.join("\n");
}

function renderBlockHtml(block: StreamBlock, mdToHtml: (md: string) => string): string {
  if (block.type === "thinking") {
    const text = block.content.slice(0, 300);
    const ellipsis = block.content.length > 300 ? "..." : "";
    return `<div class="thinking">Thinking: ${escapeHtml(text + ellipsis)}</div>`;
  }
  if (block.type === "tool_call") {
    return renderToolHtml(block, 0);
  }
  return `<div class="text-block">${mdToHtml(block.content)}</div>`;
}

function renderBlocksHtml(
  blocks: Array<Record<string, unknown>>,
  mdToHtml: (md: string) => string,
): string {
  const tree = restoreBlocks(blocks);
  return tree.map((b) => renderBlockHtml(b, mdToHtml)).join("\n");
}

export interface ExportableMessage {
  sender_type: "user" | "agent";
  content: string;
  metadata?: Record<string, unknown>;
}

/**
 * Build the full HTML body for a chat export.
 *
 * `mdToHtml` is injected so this module stays free of the marked dependency
 * and the dynamic-import boundary lives in the calling hook.
 */
export function buildExportHTML(
  messages: ExportableMessage[],
  title: string,
  mdToHtml: (md: string) => string,
): string {
  const messagesHtml = messages
    .map((msg) => {
      const role = msg.sender_type === "user" ? "User" : "Agent";
      const blocks = msg.metadata?.blocks as Array<Record<string, unknown>> | undefined;
      const body =
        blocks && blocks.length > 0
          ? renderBlocksHtml(blocks, mdToHtml)
          : `<div class="text-block">${mdToHtml(msg.content)}</div>`;
      return `<section><h3>${escapeHtml(role)}</h3>${body}</section>`;
    })
    .join("<hr />");

  return `<h1>${escapeHtml(title)}</h1>${messagesHtml}`;
}

export const PRINT_STYLES = `
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.5; color: #222; font-size: 12px; }
  h1 { border-bottom: 2px solid #eee; padding-bottom: 6px; font-size: 18px; }
  h3 { margin-bottom: 2px; font-size: 13px; }
  hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
  p { margin: 4px 0; }
  code { background: #f4f4f4; padding: 1px 3px; border-radius: 3px; font-size: 0.85em; }
  pre { background: #f4f4f4; padding: 8px; border-radius: 4px; font-size: 10px; line-height: 1.4; white-space: pre-wrap; word-break: break-all; }
  strong { font-weight: 600; }
  .thinking { background: #f9f9f0; border-left: 3px solid #d4c87a; padding: 4px 8px; margin: 4px 0; font-size: 10px; color: #666; line-height: 1.4; white-space: pre-wrap; }
  .tool-block { font-size: 10px; color: #555; margin: 2px 0; }
  .tool-block pre { font-size: 9px; margin: 2px 0; padding: 4px 6px; }
  .text-block { margin: 4px 0; }
  @media print { body { margin: 10px; } }
`;
