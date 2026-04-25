"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import { Columns2, Rows2, Maximize2, X } from "@/components/icons";
import { cn } from "@/lib/utils";
import { useTheme } from "@/features/theme/theme-provider";

interface EditDiffViewProps {
  filePath?: string;
  oldString: string;
  newString: string;
}

const DARK_VARS = {
  diffViewerBackground: "rgb(11 13 17)",
  diffViewerColor: "rgb(197 197 198)",
  addedBackground: "rgba(95, 201, 146, 0.10)",
  addedColor: "rgb(197 197 198)",
  removedBackground: "rgba(255, 99, 99, 0.10)",
  removedColor: "rgb(197 197 198)",
  wordAddedBackground: "rgba(95, 201, 146, 0.28)",
  wordRemovedBackground: "rgba(255, 99, 99, 0.28)",
  addedGutterBackground: "rgba(95, 201, 146, 0.12)",
  removedGutterBackground: "rgba(255, 99, 99, 0.12)",
  gutterBackground: "rgb(11 13 17)",
  gutterBackgroundDark: "rgb(11 13 17)",
  highlightBackground: "rgba(85, 179, 255, 0.08)",
  highlightGutterBackground: "rgba(85, 179, 255, 0.12)",
  codeFoldGutterBackground: "rgb(20 22 28)",
  codeFoldBackground: "rgb(20 22 28)",
  emptyLineBackground: "rgb(11 13 17)",
  gutterColor: "rgb(135 138 148)",
  addedGutterColor: "rgb(95 201 146)",
  removedGutterColor: "rgb(255 99 99)",
  codeFoldContentColor: "rgb(180 183 192)",
  diffViewerTitleBackground: "rgb(20 22 28)",
  diffViewerTitleColor: "rgb(236 237 240)",
  diffViewerTitleBorderColor: "rgba(255, 255, 255, 0.06)",
};

const LIGHT_VARS = {
  diffViewerBackground: "rgb(255 255 255)",
  diffViewerColor: "rgb(27 29 34)",
  addedBackground: "rgba(47, 164, 106, 0.10)",
  addedColor: "rgb(27 29 34)",
  removedBackground: "rgba(210, 81, 81, 0.10)",
  removedColor: "rgb(27 29 34)",
  wordAddedBackground: "rgba(47, 164, 106, 0.28)",
  wordRemovedBackground: "rgba(210, 81, 81, 0.28)",
  addedGutterBackground: "rgba(47, 164, 106, 0.16)",
  removedGutterBackground: "rgba(210, 81, 81, 0.16)",
  gutterBackground: "rgb(250 249 247)",
  gutterBackgroundDark: "rgb(244 242 238)",
  highlightBackground: "rgba(59, 111, 216, 0.10)",
  highlightGutterBackground: "rgba(59, 111, 216, 0.18)",
  codeFoldGutterBackground: "rgb(244 242 238)",
  codeFoldBackground: "rgb(244 242 238)",
  emptyLineBackground: "rgb(250 249 247)",
  gutterColor: "rgb(111 115 128)",
  addedGutterColor: "rgb(47 164 106)",
  removedGutterColor: "rgb(210 81 81)",
  codeFoldContentColor: "rgb(78 82 92)",
  diffViewerTitleBackground: "rgb(244 242 238)",
  diffViewerTitleColor: "rgb(27 29 34)",
  diffViewerTitleBorderColor: "rgba(60, 55, 45, 0.10)",
};

const SHARED_DIFF_STYLES = {
  contentText: {
    fontFamily:
      "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontSize: "11px",
    lineHeight: "1.55",
  },
  gutter: {
    padding: "0 8px",
    minWidth: "28px",
    fontSize: "10px",
  },
  line: {
    fontSize: "11px",
  },
  marker: {
    padding: "0 6px",
  },
} as const;

type ToolbarProps = {
  filePath?: string;
  split: boolean;
  onToggleSplit: () => void;
  expanded: boolean;
  onToggleExpanded: () => void;
};

function Toolbar({
  filePath,
  split,
  onToggleSplit,
  expanded,
  onToggleExpanded,
}: ToolbarProps) {
  return (
    <div className="flex items-center gap-2 border-b border-border-subtle bg-sunk px-2.5 py-1.5">
      {filePath && (
        <span
          className="flex-1 truncate font-mono type-caption text-fg-secondary"
          title={filePath}
        >
          {filePath}
        </span>
      )}
      {!filePath && <span className="flex-1" />}

      <button
        type="button"
        onClick={onToggleSplit}
        className={cn(
          "flex items-center gap-1 rounded-xs px-1.5 py-0.5 type-caption",
          "text-fg-muted hover:bg-hover hover:text-fg-primary",
        )}
        title={split ? "Switch to unified view" : "Switch to split view"}
      >
        {split ? (
          <Columns2 size={12} strokeWidth={1.75} />
        ) : (
          <Rows2 size={12} strokeWidth={1.75} />
        )}
        <span>{split ? "Split" : "Unified"}</span>
      </button>

      <button
        type="button"
        onClick={onToggleExpanded}
        className="rounded-xs p-1 text-fg-muted hover:bg-hover hover:text-fg-primary"
        title={expanded ? "Close overlay" : "Expand to overlay"}
      >
        {expanded ? (
          <X size={12} strokeWidth={2} />
        ) : (
          <Maximize2 size={12} strokeWidth={1.75} />
        )}
      </button>
    </div>
  );
}

export function EditDiffView({ filePath, oldString, newString }: EditDiffViewProps) {
  const [split, setSplit] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const diffStyles = useMemo(
    () => ({
      ...SHARED_DIFF_STYLES,
      variables: { dark: DARK_VARS, light: LIGHT_VARS },
    }),
    [],
  );

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [expanded]);

  const diff = (
    <ReactDiffViewer
      oldValue={oldString}
      newValue={newString}
      splitView={split}
      useDarkTheme={isDark}
      compareMethod={DiffMethod.WORDS}
      hideLineNumbers={false}
      styles={diffStyles}
    />
  );

  return (
    <>
      <div className="overflow-hidden rounded-xs border border-border-subtle">
        <Toolbar
          filePath={filePath}
          split={split}
          onToggleSplit={() => setSplit((v) => !v)}
          expanded={false}
          onToggleExpanded={() => setExpanded(true)}
        />
        <div className="max-h-80 overflow-auto">{diff}</div>
      </div>

      {expanded &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-6"
            onClick={() => setExpanded(false)}
          >
            <div
              className="flex h-full max-h-[92vh] w-full max-w-[min(1400px,95vw)] flex-col overflow-hidden rounded-md border border-border bg-canvas shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <Toolbar
                filePath={filePath}
                split={split}
                onToggleSplit={() => setSplit((v) => !v)}
                expanded={true}
                onToggleExpanded={() => setExpanded(false)}
              />
              <div className="flex-1 overflow-auto">{diff}</div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
