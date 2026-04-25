"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { useWorkspaceTree } from "../hooks/use-workspace-tree";
import { useWorkspaceEditor, type EditorPane } from "../hooks/use-workspace-editor";
import { usePanelResize } from "../hooks/use-panel-resize";
import {
  MAX_UPLOAD_BYTES,
  WorkspaceApiError,
  createDir,
  deleteEntry,
  downloadFileUrl,
  moveEntry,
  saveFile,
  uploadFile,
} from "../lib/workspace-api";
import { FileTree } from "./file-tree";
import { WorkspaceToolbar } from "./workspace-toolbar";
import { FileEditor } from "./file-editor";
import { EditorTabs, TabGhost, parseTabSortId } from "./editor-tabs";
import { ConflictDialog } from "./conflict-dialog";
import { ConfirmDialog } from "./confirm-dialog";
import {
  WorkspaceContextMenu,
  type ContextMenuItem,
} from "./workspace-context-menu";
import type { PendingNew, TreeInteractions } from "./tree-node";
import type { TreeEntry } from "../lib/workspace-api";
import { basename, joinPath, parentOf } from "../lib/paths";

interface WorkspacePanelProps {
  sessionId: string;
  onClose: () => void;
  refreshSignal?: number;
}

const TREE_WIDTH_WITH_EDITOR = 360;
const TREE_ONLY_MIN_WIDTH = 240;
const TREE_ONLY_DEFAULT_WIDTH = 360;
const TREE_PLUS_EDITOR_MIN_WIDTH = TREE_WIDTH_WITH_EDITOR + 360;
const TREE_PLUS_EDITOR_DEFAULT_WIDTH = TREE_WIDTH_WITH_EDITOR + 1024;
const CHAT_MIN_WIDTH = 480;
const SIDEBAR_COLLAPSED_WIDTH = 64; // tailwind w-16
const SIDEBAR_EXPANDED_WIDTH = 280; // tailwind w-[17.5rem]
const STORAGE_KEY_COLLAPSED = "aviary:workspace-panel-width:collapsed";
const STORAGE_KEY_EXPANDED = "aviary:workspace-panel-width:expanded";

type ContextMenuState = {
  x: number;
  y: number;
  items: ContextMenuItem[];
} | null;

type ConflictState = {
  paneId: string;
  path: string;
  code: "stale" | "exists";
  retryOverwrite: () => Promise<void>;
  onReload: () => Promise<void>;
} | null;

type ConfirmState = {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  thirdAction?: { label: string; onClick: () => void };
} | null;

export function WorkspacePanel({ sessionId, onClose, refreshSignal = 0 }: WorkspacePanelProps) {
  const tree = useWorkspaceTree(sessionId);
  const editor = useWorkspaceEditor(sessionId);
  const { collapsed: sidebarCollapsed } = useSidebar();
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [contextMenu, setContextMenu] = useState<ContextMenuState>(null);
  const [conflict, setConflict] = useState<ConflictState>(null);
  const [confirmState, setConfirmState] = useState<ConfirmState>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [pendingNew, setPendingNew] = useState<PendingNew>(null);
  const [editorCollapsed, setEditorCollapsed] = useState(false);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  const hasAnyTab = useMemo(
    () => editor.rows.some((r) => r.panes.some((p) => p.tabs.length > 0)),
    [editor.rows],
  );
  const editorOpen = hasAnyTab && !editorCollapsed;

  const openFile = useCallback(
    (path: string, opts?: { pin?: boolean; targetPaneId?: string }) => {
      setEditorCollapsed(false);
      void editor.openFile(path, opts);
    },
    [editor],
  );

  const sidebarWidth = sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_EXPANDED_WIDTH;
  const { width: panelWidth, isResizing, onMouseDown } = usePanelResize({
    storageKey: editorOpen ? STORAGE_KEY_EXPANDED : STORAGE_KEY_COLLAPSED,
    defaultWidth: editorOpen ? TREE_PLUS_EDITOR_DEFAULT_WIDTH : TREE_ONLY_DEFAULT_WIDTH,
    minWidth: editorOpen ? TREE_PLUS_EDITOR_MIN_WIDTH : TREE_ONLY_MIN_WIDTH,
    reserveForMain: sidebarWidth + CHAT_MIN_WIDTH,
  });

  // Session is switched upstream; we can't block the change, so just warn.
  const prevSessionRef = useRef(sessionId);
  useEffect(() => {
    if (prevSessionRef.current === sessionId) return;
    if (editor.hasDirty) {
      window.confirm(
        "You had unsaved changes in the previous session's workspace — they were discarded.",
      );
    }
    prevSessionRef.current = sessionId;
  }, [sessionId, editor.hasDirty]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await tree.refreshAll();
      for (const row of editor.rows) {
        for (const pane of row.panes) {
          if (pane.activeTabPath) {
            await editor.reloadTab(pane.id, pane.activeTabPath);
          }
        }
      }
    } finally {
      setRefreshing(false);
    }
  }, [tree, editor]);

  const lastSignalRef = useRef<number>(refreshSignal);
  useEffect(() => {
    if (refreshSignal === lastSignalRef.current) return;
    lastSignalRef.current = refreshSignal;
    void refresh();
  }, [refreshSignal, refresh]);

  const doSave = useCallback(
    async (paneId: string, path: string, overrideExpected?: number | null) => {
      setSaving(true);
      setError(null);
      try {
        const result = await editor.save(
          paneId,
          path,
          overrideExpected !== undefined ? { expectedMtime: overrideExpected } : undefined,
        );
        if (result.status === "conflict") {
          setConflict({
            paneId,
            path,
            code: result.code,
            retryOverwrite: async () => {
              setConflict(null);
              await doSave(paneId, path, result.currentMtime);
            },
            onReload: async () => {
              setConflict(null);
              await editor.reloadTab(paneId, path);
            },
          });
        } else if (result.status === "error") {
          setError(result.message);
        }
      } finally {
        setSaving(false);
      }
    },
    [editor],
  );

  const handleCloseTab = useCallback(
    (paneId: string, path: string) => {
      if (!editor.isTabDirty(paneId, path)) {
        editor.closeTab(paneId, path);
        return;
      }
      setConfirmState({
        title: "Unsaved changes",
        body: `${basename(path)} has unsaved changes. Save before closing, or discard?`,
        confirmLabel: "Save",
        onConfirm: async () => {
          setConfirmState(null);
          await doSave(paneId, path);
          if (!editor.isTabDirty(paneId, path)) editor.closeTab(paneId, path);
        },
        thirdAction: {
          label: "Discard",
          onClick: () => {
            setConfirmState(null);
            editor.closeTab(paneId, path);
          },
        },
      });
    },
    [editor, doSave],
  );

  const handleCloseMany = useCallback(
    (paneId: string, paths: string[]) => {
      if (paths.length === 0) return;
      const dirty = paths.filter((p) => editor.isTabDirty(paneId, p));
      if (dirty.length === 0) {
        editor.closePaths(paneId, paths);
        return;
      }
      setConfirmState({
        title: "Discard unsaved changes?",
        body: `${dirty.length} file${dirty.length > 1 ? "s have" : " has"} unsaved changes:\n${dirty.map((p) => basename(p)).join(", ")}`,
        confirmLabel: "Discard & Close",
        danger: true,
        onConfirm: () => {
          setConfirmState(null);
          editor.closePaths(paneId, paths);
        },
      });
    },
    [editor],
  );

  const handleSplit = useCallback(
    (paneId: string, path: string, direction: "horizontal" | "vertical") => {
      const result = editor.splitTab(paneId, path, direction);
      if (result === "max-cols") setError("Can't split further — already at 3 columns");
      else if (result === "max-rows") setError("Can't split further — already at 2 rows");
    },
    [editor],
  );

  const handleTabContextMenu = useCallback(
    (paneId: string, e: React.MouseEvent, path: string) => {
      const pane = editor.rows.flatMap((r) => r.panes).find((p) => p.id === paneId);
      if (!pane) return;
      const idx = pane.tabs.findIndex((t) => t.path === path);
      if (idx === -1) return;
      const allPaths = pane.tabs.map((t) => t.path);
      const others = allPaths.filter((p) => p !== path);
      const rightPaths = allPaths.slice(idx + 1);
      const leftPaths = allPaths.slice(0, idx);
      const tab = pane.tabs[idx];
      const items: ContextMenuItem[] = [
        { id: "close", label: "Close", onSelect: () => handleCloseTab(paneId, path) },
        { id: "close-others", label: "Close Others", onSelect: () => handleCloseMany(paneId, others) },
      ];
      if (rightPaths.length > 0) {
        items.push({
          id: "close-right",
          label: "Close to the Right",
          onSelect: () => handleCloseMany(paneId, rightPaths),
        });
      }
      if (leftPaths.length > 0) {
        items.push({
          id: "close-left",
          label: "Close to the Left",
          onSelect: () => handleCloseMany(paneId, leftPaths),
        });
      }
      items.push({
        id: "close-all",
        label: "Close All",
        onSelect: () => handleCloseMany(paneId, allPaths),
      });
      if (!tab.pinned) {
        items.push({
          id: "pin",
          label: "Keep Open",
          onSelect: () => editor.pinTab(paneId, path),
        });
      }
      if (editor.canSplitHorizontal(paneId)) {
        items.push({
          id: "split-h",
          label: "Split Right",
          onSelect: () => handleSplit(paneId, path, "horizontal"),
        });
      }
      if (editor.canSplitVertical()) {
        items.push({
          id: "split-v",
          label: "Split Down",
          onSelect: () => handleSplit(paneId, path, "vertical"),
        });
      }
      setContextMenu({ x: e.clientX, y: e.clientY, items });
    },
    [editor, handleCloseTab, handleCloseMany, handleSplit],
  );

  const refreshParent = useCallback(
    async (p: string) => {
      await tree.refreshPath(p);
    },
    [tree],
  );

  const startNew = useCallback((parent: string, mode: "file" | "dir") => {
    tree.ensureExpanded(parent);
    setPendingNew({ parent, mode });
  }, [tree]);

  const submitNew = useCallback(
    async (parent: string, mode: "file" | "dir", name: string) => {
      setPendingNew(null);
      setError(null);
      const target = joinPath(parent, name);
      try {
        if (mode === "dir") {
          await createDir(sessionId, target);
        } else {
          await saveFile(sessionId, target, { content: "", encoding: "utf8" });
        }
        await refreshParent(parent);
      } catch (err) {
        const msg = err instanceof WorkspaceApiError ? err.message : (err as Error).message;
        setError(msg);
      }
    },
    [sessionId, refreshParent],
  );

  const submitRename = useCallback(
    async (path: string, newName: string) => {
      setRenamingPath(null);
      setError(null);
      const parent = parentOf(path);
      const target = joinPath(parent, newName);
      if (target === path) return;
      try {
        await moveEntry(sessionId, path, target);
        editor.renameTab(path, target);
        await refreshParent(parent);
      } catch (err) {
        const msg = err instanceof WorkspaceApiError ? err.message : (err as Error).message;
        setError(msg);
      }
    },
    [sessionId, editor, refreshParent],
  );

  const confirmDelete = useCallback(
    (path: string, entry: TreeEntry) => {
      const isDir = entry.type === "dir";
      setConfirmState({
        title: isDir ? "Delete folder" : "Delete file",
        body: isDir
          ? `Delete ${entry.name} and all its contents? This cannot be undone.`
          : `Delete ${entry.name}? This cannot be undone.`,
        confirmLabel: "Delete",
        danger: true,
        onConfirm: async () => {
          setConfirmState(null);
          setError(null);
          try {
            await deleteEntry(sessionId, path, isDir);
            for (const row of editor.rows) {
              for (const pane of row.panes) {
                for (const tab of pane.tabs) {
                  if (tab.path === path || tab.path.startsWith(path + "/")) {
                    editor.closeTab(pane.id, tab.path);
                  }
                }
              }
            }
            await refreshParent(parentOf(path));
          } catch (err) {
            const msg = err instanceof WorkspaceApiError ? err.message : (err as Error).message;
            setError(msg);
          }
        },
      });
    },
    [sessionId, editor, refreshParent],
  );

  const uploadFiles = useCallback(
    async (parent: string, files: FileList) => {
      setError(null);
      for (const file of Array.from(files)) {
        if (file.size > MAX_UPLOAD_BYTES) {
          setError(`${file.name} exceeds ${MAX_UPLOAD_BYTES / (1024 * 1024)} MB limit`);
          continue;
        }
        const target = joinPath(parent, file.name);
        try {
          await uploadFile(sessionId, target, file, false);
        } catch (err) {
          if (err instanceof WorkspaceApiError && err.status === 409 && err.code === "exists") {
            const proceed = window.confirm(`${file.name} already exists. Overwrite?`);
            if (proceed) {
              try {
                await uploadFile(sessionId, target, file, true);
              } catch (err2) {
                setError(err2 instanceof Error ? err2.message : "Upload failed");
              }
            }
          } else {
            setError(err instanceof Error ? err.message : "Upload failed");
          }
        }
      }
      await refreshParent(parent);
    },
    [sessionId, refreshParent],
  );

  const triggerUpload = useCallback(
    (parent: string) => {
      const input = document.createElement("input");
      input.type = "file";
      input.multiple = true;
      input.style.position = "fixed";
      input.style.left = "-9999px";
      input.style.top = "-9999px";
      input.style.opacity = "0";
      document.body.appendChild(input);
      let cleaned = false;
      const cleanup = () => {
        if (cleaned) return;
        cleaned = true;
        if (input.parentNode) input.parentNode.removeChild(input);
      };
      input.addEventListener("change", () => {
        const files = input.files;
        cleanup();
        if (files && files.length > 0) {
          void uploadFiles(parent, files);
        }
      });
      input.addEventListener("cancel", cleanup);
      window.addEventListener("focus", () => {
        setTimeout(cleanup, 1000);
      }, { once: true });
      input.click();
    },
    [uploadFiles],
  );

  const triggerDownload = useCallback(
    (path: string) => {
      const url = downloadFileUrl(sessionId, path);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = basename(path);
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
    },
    [sessionId],
  );

  const handleTreeContextMenu = useCallback(
    (e: React.MouseEvent, payload: { path: string; entry: TreeEntry | null }) => {
      const { path, entry } = payload;
      const isRoot = path === "/";
      const isDir = entry === null || entry.type === "dir";
      const items: ContextMenuItem[] = [];

      if (!isDir && entry) {
        items.push({
          id: "open",
          label: "Open",
          icon: "open",
          onSelect: () => openFile(path, { pin: true }),
        });
      }
      if (isDir) {
        items.push(
          { id: "new-file", label: "New File", icon: "new-file", onSelect: () => startNew(path, "file") },
          { id: "new-folder", label: "New Folder", icon: "new-folder", onSelect: () => startNew(path, "dir") },
          { id: "upload", label: "Upload File…", icon: "upload", onSelect: () => triggerUpload(path) },
        );
      }
      if (!isDir && entry) {
        items.push({ id: "download", label: "Download", icon: "download", onSelect: () => triggerDownload(path) });
      }
      if (!isRoot && entry) {
        items.push({
          id: "rename",
          label: "Rename",
          icon: "rename",
          onSelect: () => setRenamingPath(path),
        });
        items.push({
          id: "delete",
          label: "Delete",
          icon: "delete",
          danger: true,
          onSelect: () => confirmDelete(path, entry),
        });
      }
      setContextMenu({ x: e.clientX, y: e.clientY, items });
    },
    [openFile, startNew, triggerUpload, triggerDownload, confirmDelete],
  );

  const ui: TreeInteractions = {
    activeFilePath: editor.activeTab?.path ?? null,
    onFileClick: (p) => openFile(p),
    onFileDoubleClick: (p) => openFile(p, { pin: true }),
    onContextMenu: handleTreeContextMenu,
    renamingPath,
    onSubmitRename: (p, v) => void submitRename(p, v),
    onCancelRename: () => setRenamingPath(null),
    pendingNew,
    onSubmitNew: (parent, mode, name) => void submitNew(parent, mode, name),
    onCancelNew: () => setPendingNew(null),
  };

  // --- Cross-pane drag-drop ---
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragStart = useCallback((e: DragStartEvent) => {
    setActiveDragId(String(e.active.id));
  }, []);

  const draggedTab = useMemo(() => {
    if (!activeDragId) return null;
    const parsed = parseTabSortId(activeDragId);
    if (!parsed) return null;
    for (const row of editor.rows) {
      for (const pane of row.panes) {
        if (pane.id !== parsed.paneId) continue;
        const t = pane.tabs.find((tab) => tab.path === parsed.path);
        if (t) return t;
      }
    }
    return null;
  }, [activeDragId, editor.rows]);

  const handleDragEnd = useCallback(
    (e: DragEndEvent) => {
      setActiveDragId(null);
      const { active, over } = e;
      if (!over) return;
      const src = parseTabSortId(String(active.id));
      const dst = parseTabSortId(String(over.id));
      if (!src || !dst) return;
      if (src.paneId === dst.paneId) {
        if (src.path === dst.path) return;
        const pane = editor.rows.flatMap((r) => r.panes).find((p) => p.id === src.paneId);
        if (!pane) return;
        const ids = pane.tabs.map((t) => t.path);
        const oldIdx = ids.indexOf(src.path);
        const newIdx = ids.indexOf(dst.path);
        if (oldIdx === -1 || newIdx === -1) return;
        editor.reorderTabs(src.paneId, arrayMove(ids, oldIdx, newIdx));
      } else {
        const dstPane = editor.rows.flatMap((r) => r.panes).find((p) => p.id === dst.paneId);
        const toIndex = dstPane ? dstPane.tabs.findIndex((t) => t.path === dst.path) : null;
        editor.moveTab(src.paneId, dst.paneId, src.path, toIndex);
      }
    },
    [editor],
  );

  return (
    <aside
      className="relative flex h-full shrink-0 bg-canvas"
      style={{ width: panelWidth }}
    >
      <ResizeHandle onMouseDown={onMouseDown} active={isResizing} />

      <div
        className={cn(
          "flex h-full flex-col border-l border-border-subtle",
          editorOpen ? "border-r border-border-subtle" : "flex-1",
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
          showExpandEditor={hasAnyTab && editorCollapsed}
          onExpandEditor={() => setEditorCollapsed(false)}
        />
        <FileTree tree={tree} ui={ui} />
      </div>

      {editorOpen && (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={() => setActiveDragId(null)}
        >
          <div className="flex h-full flex-1 min-w-0 flex-col">
            {editor.rows.map((row, rowIdx) => (
              <div
                key={row.id}
                className={cn(
                  "flex min-h-0 flex-1 min-w-0",
                  rowIdx > 0 && "border-t border-border-subtle",
                )}
              >
                {row.panes.map((pane, paneIdx) => (
                  <PaneView
                    key={pane.id}
                    sessionId={sessionId}
                    pane={pane}
                    isFirstInRow={paneIdx === 0}
                    isActive={pane.id === editor.activePaneId}
                    showCollapse={rowIdx === 0 && paneIdx === row.panes.length - 1}
                    onCollapseEditor={() => setEditorCollapsed(true)}
                    onFocus={() => editor.focusPane(pane.id)}
                    onActivateTab={(path) => editor.activate(pane.id, path)}
                    onCloseTab={(path) => handleCloseTab(pane.id, path)}
                    onPinTab={(path) => editor.pinTab(pane.id, path)}
                    onTabContextMenu={(e, path) => handleTabContextMenu(pane.id, e, path)}
                    onDraftChange={(path, value) => editor.setDraft(pane.id, path, value)}
                    onSave={(path) => void doSave(pane.id, path)}
                    saving={saving}
                    errorBanner={pane.id === editor.activePaneId ? error : null}
                    onDismissError={() => setError(null)}
                  />
                ))}
              </div>
            ))}
          </div>
          <DragOverlay dropAnimation={null}>
            {draggedTab ? <TabGhost tab={draggedTab} /> : null}
          </DragOverlay>
        </DndContext>
      )}

      {contextMenu && (
        <WorkspaceContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenu.items}
          onClose={() => setContextMenu(null)}
        />
      )}

      {conflict && (
        <ConflictDialog
          path={conflict.path}
          code={conflict.code}
          onOverwrite={() => void conflict.retryOverwrite()}
          onReload={() => void conflict.onReload()}
          onCancel={() => setConflict(null)}
        />
      )}

      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          body={confirmState.body}
          confirmLabel={confirmState.confirmLabel}
          danger={confirmState.danger}
          thirdAction={confirmState.thirdAction}
          onConfirm={confirmState.onConfirm}
          onCancel={() => setConfirmState(null)}
        />
      )}
    </aside>
  );
}

interface PaneViewProps {
  sessionId: string;
  pane: EditorPane;
  isFirstInRow: boolean;
  isActive: boolean;
  showCollapse: boolean;
  onCollapseEditor: () => void;
  onFocus: () => void;
  onActivateTab: (path: string) => void;
  onCloseTab: (path: string) => void;
  onPinTab: (path: string) => void;
  onTabContextMenu: (e: React.MouseEvent, path: string) => void;
  onDraftChange: (path: string, value: string) => void;
  onSave: (path: string) => void;
  saving: boolean;
  errorBanner: string | null;
  onDismissError: () => void;
}

function PaneView({
  sessionId, pane, isFirstInRow, isActive, showCollapse, onCollapseEditor, onFocus,
  onActivateTab, onCloseTab, onPinTab, onTabContextMenu,
  onDraftChange, onSave, saving, errorBanner, onDismissError,
}: PaneViewProps) {
  const activeTab = pane.tabs.find((t) => t.path === pane.activeTabPath) ?? null;
  return (
    <div
      className={cn(
        "flex min-w-0 min-h-0 flex-1 flex-col",
        !isFirstInRow && "border-l border-border-subtle",
        isActive && "ring-1 ring-inset ring-info/20",
      )}
      onClick={onFocus}
    >
      <EditorTabs
        paneId={pane.id}
        tabs={pane.tabs}
        activeTabPath={pane.activeTabPath}
        onActivate={onActivateTab}
        onClose={onCloseTab}
        onPin={onPinTab}
        onContextMenu={onTabContextMenu}
        onCollapseEditor={showCollapse ? onCollapseEditor : undefined}
      />
      {errorBanner && (
        <div className="shrink-0 border-b border-danger/30 bg-danger/10 px-3 py-1 type-caption text-danger">
          {errorBanner}
          <button
            type="button"
            onClick={onDismissError}
            className="ml-2 text-danger/80 hover:text-danger underline"
          >
            dismiss
          </button>
        </div>
      )}
      {activeTab && (
        <FileEditor
          sessionId={sessionId}
          tab={activeTab}
          onDraftChange={onDraftChange}
          onSave={onSave}
          saving={saving}
        />
      )}
    </div>
  );
}

interface ResizeHandleProps {
  onMouseDown: (e: React.MouseEvent) => void;
  active: boolean;
}

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
            : "bg-active group-hover:bg-info/60 group-hover:w-0.5",
        )}
      />
    </div>
  );
}
