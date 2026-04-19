"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getTree, type TreeEntry } from "../lib/workspace-api";

export interface NodeState {
  entries: TreeEntry[];
  loading: boolean;
  error: string | null;
  loaded: boolean;
}

const ROOT_PATH = "/";

function joinPath(parent: string, name: string): string {
  return parent === "/" ? `/${name}` : `${parent}/${name}`;
}

export function useWorkspaceTree(sessionId: string) {
  const [showHidden, setShowHidden] = useState(false);
  const [nodes, setNodes] = useState<Map<string, NodeState>>(() => new Map());
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set([ROOT_PATH]));
  // Bumped on sessionId / showHidden change so in-flight fetches from the
  // previous generation can't overwrite fresh listings.
  const generationRef = useRef(0);

  useEffect(() => {
    generationRef.current += 1;
    setNodes(new Map());
    setExpanded(new Set([ROOT_PATH]));
  }, [sessionId, showHidden]);

  const setNode = useCallback((
    path: string,
    patch: Partial<NodeState> | ((prev: NodeState) => NodeState),
  ) => {
    setNodes((prev) => {
      const next = new Map(prev);
      const current = next.get(path) ?? { entries: [], loading: false, error: null, loaded: false };
      next.set(path, typeof patch === "function" ? patch(current) : { ...current, ...patch });
      return next;
    });
  }, []);

  const fetchPath = useCallback(
    async (path: string): Promise<void> => {
      const gen = generationRef.current;
      setNode(path, { loading: true, error: null });
      try {
        const listing = await getTree(sessionId, path, showHidden);
        if (gen !== generationRef.current) return;
        setNode(path, {
          entries: listing.entries,
          loading: false,
          error: null,
          loaded: true,
        });
      } catch (err) {
        if (gen !== generationRef.current) return;
        const message = err instanceof Error ? err.message : "Failed to load";
        setNode(path, (prev) => ({ ...prev, loading: false, error: message }));
      }
    },
    [sessionId, showHidden, setNode],
  );

  useEffect(() => {
    void fetchPath(ROOT_PATH);
  }, [fetchPath]);

  const toggle = useCallback(
    (path: string) => {
      let wasOpen = false;
      setExpanded((prev) => {
        const next = new Set(prev);
        wasOpen = prev.has(path);
        if (wasOpen) next.delete(path);
        else next.add(path);
        return next;
      });
      if (wasOpen) return;
      const current = nodes.get(path);
      if (!current?.loaded && !current?.loading) {
        void fetchPath(path);
      }
    },
    [nodes, fetchPath],
  );

  const refreshAll = useCallback(async () => {
    await Promise.all(Array.from(expanded).map((p) => fetchPath(p)));
  }, [expanded, fetchPath]);

  const collapseAll = useCallback(() => {
    setExpanded(new Set([ROOT_PATH]));
  }, []);

  const toggleHidden = useCallback(() => {
    setShowHidden((v) => !v);
  }, []);

  return useMemo(
    () => ({
      nodes,
      expanded,
      rootPath: ROOT_PATH,
      showHidden,
      toggle,
      toggleHidden,
      refreshAll,
      collapseAll,
      joinPath,
    }),
    [nodes, expanded, showHidden, toggle, toggleHidden, refreshAll, collapseAll],
  );
}

export type WorkspaceTreeState = ReturnType<typeof useWorkspaceTree>;
