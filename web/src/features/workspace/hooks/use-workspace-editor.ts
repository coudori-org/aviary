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

export type SaveResult =
  | { status: "saved" }
  | { status: "conflict"; currentMtime: number | null; currentSize: number | null; code: "stale" | "exists" }
  | { status: "error"; message: string }
  | { status: "noop" };

interface UseWorkspaceEditorResult {
  tabs: EditorTab[];
  activeTabPath: string | null;
  activeTab: EditorTab | null;
  openFile: (path: string, opts?: { pin?: boolean }) => Promise<void>;
  pinTab: (path: string) => void;
  closeTab: (path: string) => void;
  closePaths: (paths: string[]) => void;
  activate: (path: string) => void;
  setDraft: (path: string, value: string) => void;
  save: (path: string, overrideOverwrite?: { expectedMtime: number | null }) => Promise<SaveResult>;
  reloadTab: (path: string) => Promise<void>;
  renameTab: (oldPath: string, newPath: string) => void;
  hasDirty: boolean;
  isTabDirty: (path: string) => boolean;
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

export function useWorkspaceEditor(sessionId: string): UseWorkspaceEditorResult {
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  // per-path fetch generations so concurrent loads can't clobber each other
  const generationsRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    setTabs([]);
    setActiveTabPath(null);
    generationsRef.current = new Map();
  }, [sessionId]);

  const patchTab = useCallback((path: string, patch: Partial<EditorTab>) => {
    setTabs((prev) =>
      prev.map((t) => (t.path === path ? { ...t, ...patch } : t)),
    );
  }, []);

  const applyFileContents = useCallback((path: string, file: FileContents) => {
    patchTab(path, {
      loading: false,
      error: null,
      savedContent: file.content,
      savedMtime: file.mtime,
      draft: null,
      isBinary: file.isBinary,
      size: file.size,
    });
  }, [patchTab]);

  const nextGeneration = (path: string): number => {
    const gens = generationsRef.current;
    const gen = (gens.get(path) ?? 0) + 1;
    gens.set(path, gen);
    return gen;
  };

  const loadFile = useCallback(
    async (path: string) => {
      const gen = nextGeneration(path);
      patchTab(path, { loading: true, error: null });
      try {
        const file = await getFile(sessionId, path);
        if (generationsRef.current.get(path) !== gen) return;
        applyFileContents(path, file);
      } catch (err) {
        if (generationsRef.current.get(path) !== gen) return;
        const message = err instanceof Error ? err.message : "Failed to load file";
        patchTab(path, { loading: false, error: message });
      }
    },
    [sessionId, patchTab, applyFileContents],
  );

  const openFile = useCallback(
    async (path: string, opts?: { pin?: boolean }) => {
      const pin = !!opts?.pin;
      let shouldLoad = true;
      setTabs((prev) => {
        const existing = prev.find((t) => t.path === path);
        if (existing) {
          shouldLoad = false;
          if (pin && !existing.pinned) {
            return prev.map((t) => (t.path === path ? { ...t, pinned: true } : t));
          }
          return prev;
        }
        const newTab = emptyTab(path, pin);
        // Preview mode: replace the single unpinned tab if present.
        if (!pin) {
          const previewIdx = prev.findIndex((t) => !t.pinned);
          if (previewIdx >= 0) {
            const next = [...prev];
            next[previewIdx] = newTab;
            generationsRef.current.delete(prev[previewIdx].path);
            return next;
          }
        }
        return [...prev, newTab];
      });
      setActiveTabPath(path);
      if (shouldLoad) await loadFile(path);
    },
    [loadFile],
  );

  const pinTab = useCallback((path: string) => {
    setTabs((prev) =>
      prev.map((t) => (t.path === path && !t.pinned ? { ...t, pinned: true } : t)),
    );
  }, []);

  const closeTab = useCallback((path: string) => {
    setTabs((prev) => {
      const next = prev.filter((t) => t.path !== path);
      if (activeTabPath === path) {
        const idx = prev.findIndex((t) => t.path === path);
        const nextActive =
          next[idx] ?? next[idx - 1] ?? next[0] ?? null;
        setActiveTabPath(nextActive ? nextActive.path : null);
      }
      return next;
    });
    generationsRef.current.delete(path);
  }, [activeTabPath]);

  const closePaths = useCallback((paths: string[]) => {
    if (paths.length === 0) return;
    const pathSet = new Set(paths);
    setTabs((prev) => {
      const next = prev.filter((t) => !pathSet.has(t.path));
      if (activeTabPath && pathSet.has(activeTabPath)) {
        const activeIdx = prev.findIndex((t) => t.path === activeTabPath);
        // Nearest surviving tab: prefer the one to the right, else left.
        const nextActive =
          prev.slice(activeIdx + 1).find((t) => !pathSet.has(t.path)) ??
          prev.slice(0, activeIdx).reverse().find((t) => !pathSet.has(t.path)) ??
          null;
        setActiveTabPath(nextActive ? nextActive.path : null);
      }
      return next;
    });
    for (const p of paths) generationsRef.current.delete(p);
  }, [activeTabPath]);

  const activate = useCallback((path: string) => {
    setActiveTabPath(path);
  }, []);

  // Auto-pin on first edit: once the tab has uncommitted content the user
  // clearly cares about it, so it shouldn't be replaced by the next preview.
  const setDraft = useCallback((path: string, value: string) => {
    setTabs((prev) =>
      prev.map((t) => {
        if (t.path !== path) return t;
        const draft = value === t.savedContent ? null : value;
        const pinned = t.pinned || draft !== null;
        return { ...t, draft, pinned };
      }),
    );
  }, []);

  const save = useCallback(
    async (
      path: string,
      override?: { expectedMtime: number | null },
    ): Promise<SaveResult> => {
      const tab = tabs.find((t) => t.path === path);
      if (!tab) return { status: "error", message: "Tab not found" };
      if (tab.draft === null && !override) return { status: "noop" };
      const content = tab.draft ?? tab.savedContent ?? "";
      const expectedMtime = override ? override.expectedMtime : tab.savedMtime;
      const overwrite = !!override;
      try {
        const file = await saveFile(sessionId, path, {
          content,
          encoding: "utf8",
          expectedMtime,
          overwrite,
        });
        applyFileContents(path, file);
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
    [tabs, sessionId, applyFileContents],
  );

  const reloadTab = useCallback(async (path: string) => {
    await loadFile(path);
  }, [loadFile]);

  const renameTab = useCallback((oldPath: string, newPath: string) => {
    setTabs((prev) => prev.map((t) => (t.path === oldPath ? { ...t, path: newPath } : t)));
    setActiveTabPath((cur) => (cur === oldPath ? newPath : cur));
    const gen = generationsRef.current.get(oldPath);
    if (gen !== undefined) {
      generationsRef.current.set(newPath, gen);
      generationsRef.current.delete(oldPath);
    }
  }, []);

  const activeTab = useMemo(
    () => tabs.find((t) => t.path === activeTabPath) ?? null,
    [tabs, activeTabPath],
  );

  const hasDirty = useMemo(() => tabs.some((t) => t.draft !== null), [tabs]);

  const isTabDirty = useCallback(
    (path: string) => {
      const t = tabs.find((x) => x.path === path);
      return !!t && t.draft !== null;
    },
    [tabs],
  );

  return {
    tabs,
    activeTabPath,
    activeTab,
    openFile,
    pinTab,
    closeTab,
    closePaths,
    activate,
    setDraft,
    save,
    reloadTab,
    renameTab,
    hasDirty,
    isTabDirty,
  };
}
