"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useWorkspaceTree } from "../hooks/use-workspace-tree";
import { useWorkspaceFile } from "../hooks/use-workspace-file";
import { usePanelResize } from "../hooks/use-panel-resize";
import { FileTree } from "./file-tree";
import { WorkspaceToolbar } from "./workspace-toolbar";
import { FileEditor } from "./file-editor";

interface WorkspacePanelProps {
  sessionId: string;
  onClose: () => void;
  /** Monotonic counter — whenever it changes, refetch the tree and any open file. */
  refreshSignal?: number;
}

const TREE_WIDTH_WITH_EDITOR = 360;
const TREE_ONLY_MIN_WIDTH = 240;
const TREE_ONLY_DEFAULT_WIDTH = 360;
const TREE_PLUS_EDITOR_MIN_WIDTH = TREE_WIDTH_WITH_EDITOR + 360;
const TREE_PLUS_EDITOR_DEFAULT_WIDTH = TREE_WIDTH_WITH_EDITOR + 1024;
const PANEL_MAX_WIDTH = 1800;
const CHAT_MIN_WIDTH = 320;
// Split keys so closing the editor snaps back to the user's tree-only width,
// not the expanded width they'd dragged the editor pane to.
const STORAGE_KEY_COLLAPSED = "aviary:workspace-panel-width:collapsed";
const STORAGE_KEY_EXPANDED = "aviary:workspace-panel-width:expanded";

export function WorkspacePanel({ sessionId, onClose, refreshSignal = 0 }: WorkspacePanelProps) {
  const tree = useWorkspaceTree(sessionId);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fileState = useWorkspaceFile(sessionId, activeFile);

  const editorOpen = activeFile !== null;

  const { width: panelWidth, isResizing, onMouseDown } = usePanelResize({
    storageKey: editorOpen ? STORAGE_KEY_EXPANDED : STORAGE_KEY_COLLAPSED,
    defaultWidth: editorOpen ? TREE_PLUS_EDITOR_DEFAULT_WIDTH : TREE_ONLY_DEFAULT_WIDTH,
    minWidth: editorOpen ? TREE_PLUS_EDITOR_MIN_WIDTH : TREE_ONLY_MIN_WIDTH,
    maxWidth: PANEL_MAX_WIDTH,
    reserveForMain: CHAT_MIN_WIDTH,
  });

  useEffect(() => {
    setActiveFile(null);
  }, [sessionId]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await tree.refreshAll();
      if (activeFile) {
        await fileState.reload();
      }
    } finally {
      setRefreshing(false);
    }
  }, [tree, activeFile, fileState]);

  // Skip the initial value so we don't double-fetch the tree on mount.
  const lastSignalRef = useRef<number>(refreshSignal);
  useEffect(() => {
    if (refreshSignal === lastSignalRef.current) return;
    lastSignalRef.current = refreshSignal;
    void refresh();
  }, [refreshSignal, refresh]);

  return (
    <aside
      className="relative flex h-full shrink-0 bg-base"
      style={{ width: panelWidth }}
    >
      <ResizeHandle onMouseDown={onMouseDown} active={isResizing} />

      <div
        className={cn(
          "flex h-full flex-col border-l border-white/[0.06]",
          editorOpen ? "border-r border-white/[0.06]" : "flex-1",
        )}
        style={editorOpen ? { width: TREE_WIDTH_WITH_EDITOR } : undefined}
      >
        <WorkspaceToolbar
          showHidden={tree.showHidden}
          refreshing={refreshing}
          onRefresh={() => void refresh()}
          onToggleHidden={tree.toggleHidden}
          onCollapseAll={tree.collapseAll}
          onClosePanel={onClose}
        />
        <FileTree
          tree={tree}
          activeFilePath={activeFile}
          onFileClick={setActiveFile}
        />
      </div>

      {activeFile && (
        <div className="flex h-full flex-1 min-w-0">
          <FileEditor
            path={activeFile}
            file={fileState.file}
            loading={fileState.loading}
            error={fileState.error}
            onClose={() => setActiveFile(null)}
          />
        </div>
      )}
    </aside>
  );
}

interface ResizeHandleProps {
  onMouseDown: (e: React.MouseEvent) => void;
  active: boolean;
}

// Transparent 8px hit zone straddles the panel's left edge; the 1px stripe
// inside lights up on hover/drag.
function ResizeHandle({ onMouseDown, active }: ResizeHandleProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize workspace panel"
      onMouseDown={onMouseDown}
      className={cn(
        "group absolute top-0 bottom-0 z-20 w-2 -translate-x-1/2 cursor-col-resize",
        active && "select-none",
      )}
      style={{ left: 0 }}
    >
      <div
        className={cn(
          "pointer-events-none absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-px transition-colors",
          active
            ? "bg-info/80 w-0.5"
            : "bg-white/[0.08] group-hover:bg-info/60 group-hover:w-0.5",
        )}
      />
    </div>
  );
}
