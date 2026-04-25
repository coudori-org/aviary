"use client";

import { useCallback, useState } from "react";
import { Check, Copy, WrapText } from "@/components/icons";
import { cn } from "@/lib/utils";

/**
 * CodeBlock — markdown `<pre>` renderer with a header bar (language label
 * + actions) and the canvas surface background.
 *
 * Header actions:
 *   - Wrap toggle: switches between horizontal scroll and word wrap.
 *     The active state is highlighted in info-blue so users can see at
 *     a glance which mode they're in.
 *   - Copy: copies the code text. For shell languages, leading `$ `
 *     prompts are stripped so the result is paste-ready in a terminal.
 *
 * Filename detection is intentionally not implemented — markdown code
 * blocks don't carry filename metadata reliably across agents.
 */

interface CodeBlockNodeChild {
  type?: string;
  tagName?: string;
  value?: string;
  properties?: { className?: string[] | string };
  children?: unknown[];
}

interface CodeBlockProps extends React.HTMLAttributes<HTMLPreElement> {
  node?: { children?: CodeBlockNodeChild[] };
}

const SHELL_LANGS = new Set(["bash", "sh", "shell", "zsh", "console"]);

/** Recursively extract text content from a hast node tree. */
function extractText(node: CodeBlockNodeChild): string {
  if (node.type === "text") return node.value || "";
  if (node.children) {
    return node.children
      .map((c) => extractText(c as CodeBlockNodeChild))
      .join("");
  }
  return "";
}

/** Pull the `language-xxx` class added by rehype-highlight (if any). */
function extractLanguage(node: CodeBlockNodeChild | undefined): string | null {
  if (!node) return null;
  const cls = node.properties?.className;
  const classArr = Array.isArray(cls)
    ? cls
    : typeof cls === "string"
      ? cls.split(" ")
      : [];
  for (const c of classArr) {
    if (typeof c === "string" && c.startsWith("language-")) {
      return c.slice("language-".length);
    }
  }
  return null;
}

/** Strip leading shell prompt indicators so copied commands paste cleanly. */
function stripShellPrompts(text: string): string {
  return text
    .split("\n")
    .map((line) => line.replace(/^(\s*)\$\s+/, "$1"))
    .join("\n");
}

export function CodeBlock({ children, node, className, ...props }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const [wrapped, setWrapped] = useState(false);

  const codeEl = node?.children?.find((c) => c.tagName === "code");
  const raw = codeEl ? extractText(codeEl) : "";
  const language = extractLanguage(codeEl);
  const isShell = language ? SHELL_LANGS.has(language.toLowerCase()) : false;

  const handleCopy = useCallback(async () => {
    const textToCopy = isShell ? stripShellPrompts(raw) : raw;
    await navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [raw, isShell]);

  return (
    <div className="my-3 overflow-hidden rounded-md bg-canvas border border-border-subtle">
      {/* Header bar */}
      <div className="flex items-center justify-between border-b border-border-subtle bg-hover/50 px-3 py-1.5">
        <span className="type-caption text-fg-disabled">
          {language || "text"}
        </span>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => setWrapped((w) => !w)}
            className={cn(
              "flex h-5 w-5 items-center justify-center rounded-xs transition-colors",
              wrapped
                ? "text-info hover:text-info"
                : "text-fg-muted hover:text-fg-primary",
              "hover:bg-hover",
            )}
            title={wrapped ? "Disable line wrap" : "Wrap long lines"}
            aria-label={wrapped ? "Disable line wrap" : "Wrap long lines"}
            aria-pressed={wrapped}
          >
            <WrapText size={12} strokeWidth={2} />
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="flex h-5 w-5 items-center justify-center rounded-xs text-fg-muted hover:text-fg-primary hover:bg-hover transition-colors"
            title={
              copied
                ? "Copied!"
                : isShell
                  ? "Copy as command (strips $ prompts)"
                  : "Copy"
            }
            aria-label="Copy code"
          >
            {copied ? (
              <Check size={11} strokeWidth={2.5} className="text-success" />
            ) : (
              <Copy size={11} strokeWidth={2} />
            )}
          </button>
        </div>
      </div>

      {/* Code body — pre inherits canvas bg from parent, hljs theme overlay applies */}
      <pre
        className={cn(
          "overflow-x-auto p-4 type-code",
          wrapped ? "whitespace-pre-wrap break-all" : "whitespace-pre",
          className,
        )}
        {...props}
      >
        {children}
      </pre>
    </div>
  );
}
