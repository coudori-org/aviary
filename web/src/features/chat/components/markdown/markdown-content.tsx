"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { CodeBlock } from "./code-block";

interface MarkdownContentProps {
  content: string;
}

/**
 * `components` is hoisted to module scope so each render passes the SAME
 * object reference to ReactMarkdown.
 *
 * Why this matters: ReactMarkdown invokes `React.createElement(comp, …)`
 * with whatever functions you provide. If those functions are inline-defined
 * inside a render, they're new references on every render, which React
 * treats as new component types — triggering unmount + remount of every
 * code block, link, table, etc. That blows away local state like
 * CodeBlock's `wrapped` toggle whenever any ancestor re-renders (sidebar
 * polling, scroll handlers, streaming chunks, …).
 *
 * Hoisting also means none of the renderers may close over component
 * props/state — they only get whatever ReactMarkdown passes them.
 */
const MARKDOWN_PLUGINS_REMARK = [remarkGfm];
const MARKDOWN_PLUGINS_REHYPE = [rehypeHighlight];

const MARKDOWN_COMPONENTS: Components = {
  pre: ({ children, node, ...props }) => (
    <CodeBlock node={node} {...props}>
      {children}
    </CodeBlock>
  ),
  code: ({ children, className, ...props }) => {
    const isInline = !className;
    if (isInline) {
      return (
        <code
          className="rounded-xs bg-hover px-1.5 py-0.5 type-code-sm text-accent border border-border-subtle"
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
  a: ({ children, ...props }) => (
    <a
      className="text-info underline underline-offset-2 hover:opacity-80"
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    >
      {children}
    </a>
  ),
  table: ({ children, ...props }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse type-body-tight" {...props}>
        {children}
      </table>
    </div>
  ),
  th: ({ children, ...props }) => (
    <th
      className="border border-border-subtle bg-raised px-3 py-1.5 text-left type-caption-bold"
      {...props}
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td className="border border-border-subtle px-3 py-1.5" {...props}>
      {children}
    </td>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote
      className="my-2 border-l-2 border-info/40 pl-4 text-fg-muted"
      {...props}
    >
      {children}
    </blockquote>
  ),
  ul: ({ children, ...props }) => (
    <ul className="my-2 list-disc pl-6 space-y-1" {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="my-2 list-decimal pl-6 space-y-1" {...props}>
      {children}
    </ol>
  ),
  hr: () => <hr className="my-4 border-border-subtle" />,
};

/**
 * MarkdownContent — renders ReactMarkdown with theming hooks consistent
 * with the Raycast surface system. Code blocks are delegated to CodeBlock
 * which adds a copy button and syntax highlighting.
 */
export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <ReactMarkdown
      remarkPlugins={MARKDOWN_PLUGINS_REMARK}
      rehypePlugins={MARKDOWN_PLUGINS_REHYPE}
      components={MARKDOWN_COMPONENTS}
    >
      {content}
    </ReactMarkdown>
  );
}
