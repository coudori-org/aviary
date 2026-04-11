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

    const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
      .map((node) => node.outerHTML)
      .join("\n");

    win.document.write(`<!DOCTYPE html><html><head>${styles}
      <style>
        body { background: #07080a; margin: 0; padding: 24px; }
        @media print {
          body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        }
      </style>
    </head><body>${el.innerHTML}</body></html>`);
    win.document.close();

    setTimeout(() => win.print(), 500);
  }, [containerRef]);

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
