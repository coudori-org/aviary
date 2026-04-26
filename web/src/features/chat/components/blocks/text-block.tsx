"use client";

import { memo } from "react";
import { MarkdownContent } from "@/features/chat/components/markdown/markdown-content";

/**
 * TextBlockView — agent text bubble with markdown rendering.
 * Memoized so streaming updates only re-render the latest block.
 */
export const TextBlockView = memo(function TextBlockView({ content }: { content: string }) {
  return (
    <div className="rounded-xl rounded-tl-sm bg-raised border border-border-subtle shadow-sm px-4 py-3 transition-shadow">
      <div className="markdown-body break-words type-body text-fg-secondary">
        <MarkdownContent content={content} />
      </div>
    </div>
  );
});
