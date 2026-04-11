/**
 * Export helpers — turn a list of messages into printable HTML.
 *
 * The pipeline produces final HTML directly (not markdown) so that tool
 * call results can be rendered as raw `<pre>` text without going through
 * any markdown parser. Only user/agent text-block content is passed
 * through the markdown renderer (`mdToHtml`) — tool blocks, thinking,
 * and structural chrome are built as plain HTML strings.
 *
 * Why: a previous version mixed everything into one markdown string and
 * fed it to marked, which then re-interpreted markdown syntax inside
 * tool result `<pre>` blocks (asterisks, backticks, etc were being
 * formatted instead of shown literally).
 */

type Block = Record<string, unknown>;

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

function renderToolTreeHtml(tools: Block[], indent: number): string {
  return tools
    .map((t) => {
      const parts: string[] = [];
      const name = String(t.name ?? "unknown");
      const err = t.is_error ? " [ERROR]" : "";
      parts.push(`<div class="tool-block" style="margin-left:${indent * 12}px">`);
      parts.push(`<strong>Tool: ${escapeHtml(name)}</strong>${err}`);

      const input = t.input as Record<string, unknown> | undefined;
      if (input && Object.keys(input).length > 0) {
        parts.push(`<pre>${escapeHtml(JSON.stringify(input, null, 2))}</pre>`);
      }
      if (t.result != null) {
        const result = String(t.result);
        const short = result.length > 2000 ? result.slice(0, 2000) + "\n..." : result;
        parts.push(`<pre>${escapeHtml(short)}</pre>`);
      }
      const children = t.children as Block[] | undefined;
      if (children && children.length > 0) {
        parts.push(renderToolTreeHtml(children, indent + 1));
      }
      parts.push("</div>");
      return parts.join("\n");
    })
    .join("\n");
}

function renderBlocksHtml(blocks: Block[], mdToHtml: (md: string) => string): string {
  // Build subagent nesting tree (mirrors `buildBlockTree` but on raw saved metadata)
  const toolMap = new Map<string, Block & { children: Block[] }>();
  const roots: Block[] = [];
  for (const b of blocks) {
    if (b.type === "tool_call") {
      const node = { ...b, children: [] as Block[] };
      toolMap.set(String(b.tool_use_id ?? b.id ?? ""), node);
      if (b.parent_tool_use_id) {
        const parent = toolMap.get(String(b.parent_tool_use_id));
        if (parent) {
          parent.children.push(node);
          continue;
        }
      }
      roots.push(node);
    } else {
      roots.push(b);
    }
  }

  return roots
    .map((b) => {
      if (b.type === "thinking") {
        const text = String(b.content ?? "").slice(0, 300);
        const ellipsis = String(b.content ?? "").length > 300 ? "..." : "";
        return `<div class="thinking">Thinking: ${escapeHtml(text + ellipsis)}</div>`;
      }
      if (b.type === "tool_call") {
        return renderToolTreeHtml([b], 0);
      }
      // Text block — only this branch goes through markdown rendering.
      return `<div class="text-block">${mdToHtml(String(b.content ?? ""))}</div>`;
    })
    .join("\n");
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
      const blocks = msg.metadata?.blocks as Block[] | undefined;
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
