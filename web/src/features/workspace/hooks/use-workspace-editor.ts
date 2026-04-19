"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getFile,
  saveFile,
  type FileContents,
  WorkspaceApiError,
} from "../lib/workspace-api";

export interface EditorTab {
  path: string;
  loading: boolean;
  error: string | null;
  savedContent: string | null;
  savedMtime: number | null;
  draft: string | null;
  isBinary: boolean;
  size: number;
  pinned: boolean;
}

export interface EditorPane {
  id: string;
  tabs: EditorTab[];
  activeTabPath: string | null;
}

export interface EditorRow {
  id: string;
  panes: EditorPane[];
}

export type SplitDirection = "horizontal" | "vertical";

export type SaveResult =
  | { status: "saved" }
  | { status: "conflict"; currentMtime: number | null; currentSize: number | null; code: "stale" | "exists" }
  | { status: "error"; message: string }
  | { status: "noop" };

export type SplitResult = "ok" | "max-cols" | "max-rows";

const MAX_COLS = 3;
const MAX_ROWS = 2;

interface UseWorkspaceEditorResult {
  rows: EditorRow[];
  activePaneId: string;
  activeTab: EditorTab | null;
  findTab: (paneId: string, path: string) => EditorTab | null;

  openFile: (path: string, opts?: { pin?: boolean; targetPaneId?: string }) => Promise<void>;
  focusPane: (paneId: string) => void;
  pinTab: (paneId: string, path: string) => void;
  closeTab: (paneId: string, path: string) => void;
  closePaths: (paneId: string, paths: string[]) => void;
  reorderTabs: (paneId: string, orderedPaths: string[]) => void;
  activate: (paneId: string, path: string) => void;
  setDraft: (paneId: string, path: string, value: string) => void;
  save: (paneId: string, path: string, overrideOverwrite?: { expectedMtime: number | null }) => Promise<SaveResult>;
  reloadTab: (paneId: string, path: string) => Promise<void>;
  renameTab: (oldPath: string, newPath: string) => void;

  splitTab: (fromPaneId: string, path: string, direction: SplitDirection) => SplitResult;
  moveTab: (fromPaneId: string, toPaneId: string, path: string, toIndex: number | null) => void;

  hasDirty: boolean;
  canSplitHorizontal: (paneId: string) => boolean;
  canSplitVertical: () => boolean;
  isTabDirty: (paneId: string, path: string) => boolean;
}

const emptyTab = (path: string, pinned: boolean): EditorTab => ({
  path,
  loading: true,
  error: null,
  savedContent: null,
  savedMtime: null,
  draft: null,
  isBinary: false,
  size: 0,
  pinned,
});

let globalIdCounter = 0;
const genId = (prefix: string) => `${prefix}_${Date.now().toString(36)}_${++globalIdCounter}`;

const initialState = (): { rows: EditorRow[]; activePaneId: string } => {
  const paneId = "pane_root";
  return {
    rows: [{ id: "row_root", panes: [{ id: paneId, tabs: [], activeTabPath: null }] }],
    activePaneId: paneId,
  };
};

function findPaneIn(rows: EditorRow[], paneId: string): { rowIdx: number; paneIdx: number; pane: EditorPane } | null {
  for (let ri = 0; ri < rows.length; ri++) {
    const pi = rows[ri].panes.findIndex((p) => p.id === paneId);
    if (pi >= 0) return { rowIdx: ri, paneIdx: pi, pane: rows[ri].panes[pi] };
  }
  return null;
}

function findTabPane(rows: EditorRow[], path: string): EditorPane | null {
  for (const row of rows) for (const pane of row.panes) {
    if (pane.tabs.some((t) => t.path === path)) return pane;
  }
  return null;
}

/** Flatten all panes, in row-major order. */
function allPanes(rows: EditorRow[]): EditorPane[] {
  const out: EditorPane[] = [];
  for (const row of rows) out.push(...row.panes);
  return out;
}

/** Compute next-active path within a pane after removing `removedPath`. */
function nextActiveAfterRemoval(tabs: EditorTab[], removedIdx: number): string | null {
  if (tabs.length <= 1) return null;
  // tabs here is PRE-removal. After removal, prefer same-position, else previous.
  const nextIdx = removedIdx < tabs.length - 1 ? removedIdx + 1 : removedIdx - 1;
  return tabs[nextIdx]?.path ?? null;
}

/** Remove a pane from rows; if its row becomes empty, drop the row too. Keeps
 *  at least one row+pane alive. */
function dropPane(rows: EditorRow[], paneId: string): EditorRow[] {
  const next = rows.map((r) => ({ ...r, panes: r.panes.filter((p) => p.id !== paneId) }))
                   .filter((r) => r.panes.length > 0);
  if (next.length === 0) {
    const fresh = initialState();
    return fresh.rows;
  }
  return next;
}

/** Pick a surviving pane to focus when the active one was dropped. */
function chooseFallbackPane(rows: EditorRow[]): string {
  return allPanes(rows)[0].id;
}

export function useWorkspaceEditor(sessionId: string): UseWorkspaceEditorResult {
  const [rows, setRows] = useState<EditorRow[]>(() => initialState().rows);
  const [activePaneId, setActivePaneId] = useState<string>(() => initialState().activePaneId);
  // Per-(pane, path) fetch generations so concurrent loads can't clobber each other.
  const generationsRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const fresh = initialState();
    setRows(fresh.rows);
    setActivePaneId(fresh.activePaneId);
    generationsRef.current = new Map();
  }, [sessionId]);

  const genKey = (paneId: string, path: string) => `${paneId}::${path}`;
  const nextGeneration = (key: string): number => {
    const g = (generationsRef.current.get(key) ?? 0) + 1;
    generationsRef.current.set(key, g);
    return g;
  };

  const patchTab = useCallback((paneId: string, path: string, patch: Partial<EditorTab>) => {
    setRows((prev) => prev.map((row) => ({
      ...row,
      panes: row.panes.map((p) => {
        if (p.id !== paneId) return p;
        return { ...p, tabs: p.tabs.map((t) => t.path === path ? { ...t, ...patch } : t) };
      }),
    })));
  }, []);

  const applyFileContents = useCallback((paneId: string, path: string, file: FileContents) => {
    patchTab(paneId, path, {
      loading: false,
      error: null,
      savedContent: file.content,
      savedMtime: file.mtime,
      draft: null,
      isBinary: file.isBinary,
      size: file.size,
    });
  }, [patchTab]);

  const loadFile = useCallback(async (paneId: string, path: string) => {
    const key = genKey(paneId, path);
    const gen = nextGeneration(key);
    patchTab(paneId, path, { loading: true, error: null });
    try {
      const file = await getFile(sessionId, path);
      if (generationsRef.current.get(key) !== gen) return;
      applyFileContents(paneId, path, file);
    } catch (err) {
      if (generationsRef.current.get(key) !== gen) return;
      const message = err instanceof Error ? err.message : "Failed to load file";
      patchTab(paneId, path, { loading: false, error: message });
    }
  }, [sessionId, patchTab, applyFileContents]);

  const focusPane = useCallback((paneId: string) => {
    setActivePaneId(paneId);
  }, []);

  const openFile = useCallback(
    async (path: string, opts?: { pin?: boolean; targetPaneId?: string }) => {
      const pin = !!opts?.pin;
      // If file already open anywhere, activate there; otherwise use target/active pane.
      const existing = findTabPane(rows, path);
      const targetPaneId = existing?.id ?? opts?.targetPaneId ?? activePaneId;
      const shouldLoad = !existing;

      setRows((prev) => prev.map((row) => ({
        ...row,
        panes: row.panes.map((pane) => {
          if (pane.id !== targetPaneId) return pane;
          const existingTab = pane.tabs.find((t) => t.path === path);
          if (existingTab) {
            return {
              ...pane,
              activeTabPath: path,
              tabs: pin && !existingTab.pinned
                ? pane.tabs.map((t) => (t.path === path ? { ...t, pinned: true } : t))
                : pane.tabs,
            };
          }
          const newTab = emptyTab(path, pin);
          if (!pin) {
            const previewIdx = pane.tabs.findIndex((t) => !t.pinned);
            if (previewIdx >= 0) {
              generationsRef.current.delete(genKey(pane.id, pane.tabs[previewIdx].path));
              const nextTabs = [...pane.tabs];
              nextTabs[previewIdx] = newTab;
              return { ...pane, tabs: nextTabs, activeTabPath: path };
            }
          }
          return { ...pane, tabs: [...pane.tabs, newTab], activeTabPath: path };
        }),
      })));
      setActivePaneId(targetPaneId);
      if (shouldLoad) await loadFile(targetPaneId, path);
    },
    [rows, activePaneId, loadFile],
  );

  const pinTab = useCallback((paneId: string, path: string) => {
    patchTab(paneId, path, { pinned: true });
  }, [patchTab]);

  const closeTab = useCallback((paneId: string, path: string) => {
    setRows((prev) => {
      const paneRef = findPaneIn(prev, paneId);
      if (!paneRef) return prev;
      const { pane } = paneRef;
      const idx = pane.tabs.findIndex((t) => t.path === path);
      if (idx === -1) return prev;
      const remaining = pane.tabs.filter((_, i) => i !== idx);
      generationsRef.current.delete(genKey(paneId, path));

      // Pane becomes empty → drop it.
      if (remaining.length === 0) {
        const next = dropPane(prev, paneId);
        if (activePaneId === paneId) {
          setActivePaneId(chooseFallbackPane(next));
        }
        return next;
      }

      const nextActive =
        pane.activeTabPath === path
          ? nextActiveAfterRemoval(pane.tabs, idx)
          : pane.activeTabPath;
      return prev.map((row) => ({
        ...row,
        panes: row.panes.map((p) =>
          p.id !== paneId ? p : { ...p, tabs: remaining, activeTabPath: nextActive },
        ),
      }));
    });
  }, [activePaneId]);

  const closePaths = useCallback((paneId: string, paths: string[]) => {
    if (paths.length === 0) return;
    const pathSet = new Set(paths);
    setRows((prev) => {
      const paneRef = findPaneIn(prev, paneId);
      if (!paneRef) return prev;
      const { pane } = paneRef;
      const remaining = pane.tabs.filter((t) => !pathSet.has(t.path));
      for (const p of paths) generationsRef.current.delete(genKey(paneId, p));

      if (remaining.length === 0) {
        const next = dropPane(prev, paneId);
        if (activePaneId === paneId) {
          setActivePaneId(chooseFallbackPane(next));
        }
        return next;
      }

      let nextActive = pane.activeTabPath;
      if (nextActive && pathSet.has(nextActive)) {
        const activeIdx = pane.tabs.findIndex((t) => t.path === nextActive);
        const fallback =
          pane.tabs.slice(activeIdx + 1).find((t) => !pathSet.has(t.path)) ??
          pane.tabs.slice(0, activeIdx).reverse().find((t) => !pathSet.has(t.path)) ??
          null;
        nextActive = fallback?.path ?? null;
      }

      return prev.map((row) => ({
        ...row,
        panes: row.panes.map((p) =>
          p.id !== paneId ? p : { ...p, tabs: remaining, activeTabPath: nextActive },
        ),
      }));
    });
  }, [activePaneId]);

  const reorderTabs = useCallback((paneId: string, orderedPaths: string[]) => {
    setRows((prev) => prev.map((row) => ({
      ...row,
      panes: row.panes.map((p) => {
        if (p.id !== paneId) return p;
        const byPath = new Map(p.tabs.map((t) => [t.path, t]));
        const reordered: EditorTab[] = [];
        for (const op of orderedPaths) {
          const t = byPath.get(op);
          if (t) { reordered.push(t); byPath.delete(op); }
        }
        for (const t of byPath.values()) reordered.push(t);
        return { ...p, tabs: reordered };
      }),
    })));
  }, []);

  const activate = useCallback((paneId: string, path: string) => {
    setRows((prev) => prev.map((row) => ({
      ...row,
      panes: row.panes.map((p) => (p.id === paneId ? { ...p, activeTabPath: path } : p)),
    })));
    setActivePaneId(paneId);
  }, []);

  // Auto-pin on first edit.
  const setDraft = useCallback((paneId: string, path: string, value: string) => {
    setRows((prev) => prev.map((row) => ({
      ...row,
      panes: row.panes.map((p) => {
        if (p.id !== paneId) return p;
        return {
          ...p,
          tabs: p.tabs.map((t) => {
            if (t.path !== path) return t;
            const draft = value === t.savedContent ? null : value;
            const pinned = t.pinned || draft !== null;
            return { ...t, draft, pinned };
          }),
        };
      }),
    })));
  }, []);

  const save = useCallback(
    async (
      paneId: string,
      path: string,
      override?: { expectedMtime: number | null },
    ): Promise<SaveResult> => {
      const paneRef = findPaneIn(rows, paneId);
      if (!paneRef) return { status: "error", message: "Pane not found" };
      const tab = paneRef.pane.tabs.find((t) => t.path === path);
      if (!tab) return { status: "error", message: "Tab not found" };
      if (tab.draft === null && !override) return { status: "noop" };
      const content = tab.draft ?? tab.savedContent ?? "";
      const expectedMtime = override ? override.expectedMtime : tab.savedMtime;
      const overwrite = !!override;
      try {
        const file = await saveFile(sessionId, path, {
          content, encoding: "utf8", expectedMtime, overwrite,
        });
        applyFileContents(paneId, path, file);
        return { status: "saved" };
      } catch (err) {
        if (err instanceof WorkspaceApiError && err.status === 409 && (err.code === "stale" || err.code === "exists")) {
          return {
            status: "conflict",
            currentMtime: err.currentMtime,
            currentSize: err.currentSize,
            code: err.code,
          };
        }
        const message = err instanceof Error ? err.message : "Save failed";
        return { status: "error", message };
      }
    },
    [rows, sessionId, applyFileContents],
  );

  const reloadTab = useCallback(async (paneId: string, path: string) => {
    await loadFile(paneId, path);
  }, [loadFile]);

  const renameTab = useCallback((oldPath: string, newPath: string) => {
    setRows((prev) => prev.map((row) => ({
      ...row,
      panes: row.panes.map((pane) => {
        const hasTab = pane.tabs.some((t) => t.path === oldPath);
        if (!hasTab) return pane;
        const oldGen = generationsRef.current.get(genKey(pane.id, oldPath));
        if (oldGen !== undefined) {
          generationsRef.current.set(genKey(pane.id, newPath), oldGen);
          generationsRef.current.delete(genKey(pane.id, oldPath));
        }
        return {
          ...pane,
          tabs: pane.tabs.map((t) => (t.path === oldPath ? { ...t, path: newPath } : t)),
          activeTabPath: pane.activeTabPath === oldPath ? newPath : pane.activeTabPath,
        };
      }),
    })));
  }, []);

  const splitTab = useCallback(
    (fromPaneId: string, path: string, direction: SplitDirection): SplitResult => {
      let outcome: SplitResult = "ok";
      let newPaneId: string | null = null;
      setRows((prev) => {
        const ref = findPaneIn(prev, fromPaneId);
        if (!ref) return prev;
        const { rowIdx, paneIdx, pane } = ref;
        const tab = pane.tabs.find((t) => t.path === path);
        if (!tab) return prev;

        if (direction === "horizontal" && prev[rowIdx].panes.length >= MAX_COLS) {
          outcome = "max-cols";
          return prev;
        }
        if (direction === "vertical" && prev.length >= MAX_ROWS) {
          outcome = "max-rows";
          return prev;
        }

        const sole = pane.tabs.length === 1;
        // Source pane tabs after split: same if sole (duplicate), else tab removed.
        const srcTabs = sole ? pane.tabs : pane.tabs.filter((t) => t.path !== path);
        const srcActive = sole
          ? pane.activeTabPath
          : (pane.activeTabPath === path
              ? nextActiveAfterRemoval(pane.tabs, paneIdx >= 0 ? pane.tabs.findIndex((t) => t.path === path) : 0)
              : pane.activeTabPath);

        newPaneId = genId("pane");
        const newPane: EditorPane = {
          id: newPaneId,
          tabs: [{ ...tab }], // fresh copy; separate generation key
          activeTabPath: path,
        };

        if (direction === "horizontal") {
          return prev.map((row, ri) => {
            if (ri !== rowIdx) return row;
            const panes = row.panes.map((p) =>
              p.id === fromPaneId ? { ...p, tabs: srcTabs, activeTabPath: srcActive } : p,
            );
            panes.splice(paneIdx + 1, 0, newPane);
            return { ...row, panes };
          });
        }
        // vertical — add a new row below the source row
        const next = prev.map((row, ri) => {
          if (ri !== rowIdx) return row;
          return {
            ...row,
            panes: row.panes.map((p) =>
              p.id === fromPaneId ? { ...p, tabs: srcTabs, activeTabPath: srcActive } : p,
            ),
          };
        });
        next.splice(rowIdx + 1, 0, { id: genId("row"), panes: [newPane] });
        return next;
      });

      if (outcome === "ok" && newPaneId) {
        setActivePaneId(newPaneId);
      }
      return outcome;
    },
    [],
  );

  const moveTab = useCallback(
    (fromPaneId: string, toPaneId: string, path: string, toIndex: number | null) => {
      if (fromPaneId === toPaneId) return;
      setRows((prev) => {
        const fromRef = findPaneIn(prev, fromPaneId);
        const toRef = findPaneIn(prev, toPaneId);
        if (!fromRef || !toRef) return prev;
        const tab = fromRef.pane.tabs.find((t) => t.path === path);
        if (!tab) return prev;
        if (toRef.pane.tabs.some((t) => t.path === path)) {
          // Already exists in target — just drop from source, activate there.
          return afterDrop(prev, fromPaneId, path, toPaneId);
        }

        const srcTabs = fromRef.pane.tabs.filter((t) => t.path !== path);
        const srcActive = fromRef.pane.activeTabPath === path
          ? nextActiveAfterRemoval(fromRef.pane.tabs, fromRef.pane.tabs.findIndex((t) => t.path === path))
          : fromRef.pane.activeTabPath;

        const insertIdx = toIndex === null ? toRef.pane.tabs.length : Math.min(Math.max(toIndex, 0), toRef.pane.tabs.length);
        const dstTabs = [...toRef.pane.tabs];
        dstTabs.splice(insertIdx, 0, { ...tab });

        generationsRef.current.delete(genKey(fromPaneId, path));

        if (srcTabs.length === 0) {
          // Source pane empties — drop it.
          const without = dropPane(
            prev.map((row) => ({
              ...row,
              panes: row.panes.map((p) =>
                p.id === toPaneId ? { ...p, tabs: dstTabs, activeTabPath: path } : p,
              ),
            })),
            fromPaneId,
          );
          return without;
        }

        return prev.map((row) => ({
          ...row,
          panes: row.panes.map((p) => {
            if (p.id === fromPaneId) return { ...p, tabs: srcTabs, activeTabPath: srcActive };
            if (p.id === toPaneId) return { ...p, tabs: dstTabs, activeTabPath: path };
            return p;
          }),
        }));
      });
      setActivePaneId(toPaneId);
    },
    [],
  );

  const findTab = useCallback((paneId: string, path: string): EditorTab | null => {
    const ref = findPaneIn(rows, paneId);
    if (!ref) return null;
    return ref.pane.tabs.find((t) => t.path === path) ?? null;
  }, [rows]);

  const activeTab = useMemo(() => {
    const ref = findPaneIn(rows, activePaneId);
    if (!ref || !ref.pane.activeTabPath) return null;
    return ref.pane.tabs.find((t) => t.path === ref.pane.activeTabPath) ?? null;
  }, [rows, activePaneId]);

  const hasDirty = useMemo(() => {
    for (const row of rows) for (const pane of row.panes) {
      if (pane.tabs.some((t) => t.draft !== null)) return true;
    }
    return false;
  }, [rows]);

  const isTabDirty = useCallback((paneId: string, path: string) => {
    const ref = findPaneIn(rows, paneId);
    if (!ref) return false;
    const t = ref.pane.tabs.find((x) => x.path === path);
    return !!t && t.draft !== null;
  }, [rows]);

  const canSplitHorizontal = useCallback((paneId: string) => {
    const ref = findPaneIn(rows, paneId);
    return !!ref && rows[ref.rowIdx].panes.length < MAX_COLS;
  }, [rows]);

  const canSplitVertical = useCallback(() => rows.length < MAX_ROWS, [rows]);

  return {
    rows,
    activePaneId,
    activeTab,
    findTab,
    openFile,
    focusPane,
    pinTab,
    closeTab,
    closePaths,
    reorderTabs,
    activate,
    setDraft,
    save,
    reloadTab,
    renameTab,
    splitTab,
    moveTab,
    hasDirty,
    canSplitHorizontal,
    canSplitVertical,
    isTabDirty,
  };
}

/** Post-drop state update when the tab already exists in the target pane. */
function afterDrop(
  rows: EditorRow[],
  fromPaneId: string,
  path: string,
  toPaneId: string,
): EditorRow[] {
  const fromRef = findPaneIn(rows, fromPaneId);
  if (!fromRef) return rows;
  const srcTabs = fromRef.pane.tabs.filter((t) => t.path !== path);
  const srcActive =
    fromRef.pane.activeTabPath === path
      ? nextActiveAfterRemoval(fromRef.pane.tabs, fromRef.pane.tabs.findIndex((t) => t.path === path))
      : fromRef.pane.activeTabPath;

  const stripped = rows.map((row) => ({
    ...row,
    panes: row.panes.map((p) =>
      p.id === fromPaneId ? { ...p, tabs: srcTabs, activeTabPath: srcActive } :
      p.id === toPaneId ? { ...p, activeTabPath: path } : p,
    ),
  }));

  if (srcTabs.length === 0) {
    return dropPane(stripped, fromPaneId);
  }
  return stripped;
}
