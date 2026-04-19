"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Code2, Eye, Loader2, X } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { FileContents } from "../lib/workspace-api";
import { monacoLanguageFor } from "../lib/file-icons";
import { MarkdownContent } from "@/features/chat/components/markdown/markdown-content";

// Monaco is a large client-only bundle; Next.js SSR explicitly disabled.
const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  { ssr: false, loading: () => <EditorLoading /> },
);

interface FileEditorProps {
  path: string;
  file: FileContents | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

function isMarkdownPath(p: string): boolean {
  const ext = p.slice(p.lastIndexOf(".") + 1).toLowerCase();
  return ext === "md" || ext === "markdown";
}

export function FileEditor({ path, file, loading, error, onClose }: FileEditorProps) {
  const language = useMemo(() => {
    const base = path.slice(path.lastIndexOf("/") + 1);
    return monacoLanguageFor(base);
  }, [path]);
  const isMarkdown = useMemo(() => isMarkdownPath(path), [path]);

  // Default markdown files to preview; remember per-path so switching files
  // doesn't leak the previous one's mode.
  const [preview, setPreview] = useState(false);
  useEffect(() => {
    setPreview(isMarkdown);
  }, [path, isMarkdown]);

  return (
    <div className="flex h-full flex-1 flex-col min-w-0 border-l border-white/[0.06] bg-canvas">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-1.5">
        <span className="truncate type-caption text-fg-muted font-mono" title={path}>
          {path}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          {isMarkdown && (
            <button
              type="button"
              onClick={() => setPreview((v) => !v)}
              title={preview ? "View source" : "View preview"}
              aria-label={preview ? "View markdown source" : "View markdown preview"}
              aria-pressed={preview}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-xs transition-colors",
                preview
                  ? "bg-raised text-fg-primary"
                  : "text-fg-muted hover:bg-raised hover:text-fg-primary",
              )}
            >
              {preview ? <Code2 size={12} strokeWidth={2} /> : <Eye size={12} strokeWidth={2} />}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            title="Close file"
            aria-label="Close file"
            className="flex h-6 w-6 items-center justify-center rounded-xs text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors"
          >
            <X size={12} strokeWidth={2} />
          </button>
        </div>
      </header>

      <div className="flex-1 min-h-0">
        {loading ? (
          <EditorLoading />
        ) : error ? (
          <div className="flex h-full items-center justify-center px-4">
            <div className="flex items-center gap-2 type-caption text-danger/80">
              <AlertTriangle size={14} strokeWidth={2} />
              {error}
            </div>
          </div>
        ) : file?.isBinary ? (
          <div className="flex h-full items-center justify-center px-4 type-caption text-fg-muted text-center">
            Binary file — {formatSize(file.size)}. Preview not available.
          </div>
        ) : file && isMarkdown && preview ? (
          <div className="prose prose-invert h-full overflow-auto px-6 py-4 max-w-none">
            <MarkdownContent content={file.content} />
          </div>
        ) : file ? (
          <MonacoEditor
            height="100%"
            theme="vs-dark"
            language={language}
            value={file.content}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 13,
              wordWrap: "on",
              renderWhitespace: "selection",
              scrollBeyondLastLine: false,
              lineNumbersMinChars: 3,
              folding: true,
              automaticLayout: true,
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function EditorLoading() {
  return (
    <div className="flex h-full items-center justify-center gap-2 type-caption text-fg-muted">
      <Loader2 size={14} className="animate-spin" strokeWidth={2} />
      Loading…
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
