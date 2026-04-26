"use client";

import { useCallback, type RefObject } from "react";
import { buildExportHTML, PRINT_STYLES } from "@/features/chat/lib/export-formats";
import type { Message, Session } from "@/types";

interface UseChatExportOptions {
  containerRef: RefObject<HTMLElement | null>;
  messages: Message[];
  session: Session | null;
}

/**
 * useChatExport — two export flows:
 *
 *   1. printVisual: opens a new window with the live chat DOM cloned in,
 *      preserving the dark theme and all styles. Triggers print dialog.
 *
 *   2. exportText: builds a clean markdown representation, opens a new
 *      window with light-theme print styles, triggers print.
 */
export function useChatExport({ containerRef, messages, session }: UseChatExportOptions) {
  const printVisual = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;

    const win = window.open("", "_blank");
    if (!win) return;

    const html = document.documentElement;
    const theme = html.getAttribute("data-theme") ?? "dark";
    const accent = html.getAttribute("data-accent") ?? "blue";
    const bodyClass = document.body.className;
    const titleText = (session?.title || "Chat").replace(/[<&>]/g, "");

    const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
      .map((node) => node.outerHTML)
      .join("\n");

    win.document.write(`<!DOCTYPE html>
<html lang="en" data-theme="${theme}" data-accent="${accent}">
<head>
  <meta charset="utf-8" />
  <title>${titleText}</title>
  ${styles}
  <style>
    html, body { background: var(--bg-canvas); color: var(--fg-primary); margin: 0; }
    body { padding: 24px; }
    /* Neutralize the live-app scroll container so the entire transcript prints. */
    body > [data-print-root] { position: static !important; inset: auto !important; height: auto !important; overflow: visible !important; }
    body > [data-print-root] > * { position: static !important; inset: auto !important; height: auto !important; overflow: visible !important; }
    .print-header { margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border-subtle); }
    .print-header-title { font-size: 16px; font-weight: 600; color: var(--fg-primary); }
    .print-header-meta { font-size: 11px; color: var(--fg-tertiary); margin-top: 2px; }
    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; padding: 0; }
    }
  </style>
</head>
<body class="${bodyClass}">
  <div class="print-header">
    <div class="print-header-title">${titleText}</div>
    <div class="print-header-meta">${new Date().toLocaleString()}</div>
  </div>
  <div data-print-root>${el.innerHTML}</div>
</body>
</html>`);
    win.document.close();

    setTimeout(() => win.print(), 500);
  }, [containerRef, session]);

  const exportText = useCallback(async () => {
    if (messages.length === 0) return;

    const title = session?.title || "Chat Export";

    // marked is dynamically imported to keep it out of the main bundle.
    // It's only used for the inner content of text blocks — tool blocks
    // bypass it entirely so their results render as raw <pre> text.
    const { marked } = await import("marked");
    const mdToHtml = (md: string) => marked.parse(md) as string;
    const bodyHtml = buildExportHTML(messages, title, mdToHtml);

    const win = window.open("", "_blank");
    if (!win) return;

    win.document.write(`<!DOCTYPE html><html><head>
      <style>${PRINT_STYLES}</style>
    </head><body>${bodyHtml}</body></html>`);
    win.document.close();

    setTimeout(() => win.print(), 500);
  }, [messages, session]);

  return { printVisual, exportText };
}
