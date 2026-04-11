"use client";

import { useCallback, useState } from "react";
import { Check, Copy } from "@/components/icons";

export function MessageCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="mt-1 inline-flex items-center gap-1 rounded-xs px-2 py-0.5 type-caption text-fg-disabled transition-colors hover:text-fg-muted"
      title="Copy message"
    >
      {copied ? (
        <>
          <Check size={11} strokeWidth={2.5} /> Copied
        </>
      ) : (
        <>
          <Copy size={11} strokeWidth={2} /> Copy
        </>
      )}
    </button>
  );
}
