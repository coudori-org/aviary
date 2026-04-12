import { useCallback, useRef } from "react";

interface Snapshot {
  nodes: unknown[];
  edges: unknown[];
}

const MAX_HISTORY = 50;

/**
 * Standalone undo/redo stack. Does NOT own React state — the caller
 * (provider) owns nodes/edges via useNodesState/useEdgesState and
 * calls push/undo/redo imperatively.
 */
export function useWorkflowHistory() {
  const pastRef = useRef<Snapshot[]>([]);
  const futureRef = useRef<Snapshot[]>([]);

  const push = useCallback((snapshot: Snapshot) => {
    pastRef.current = [...pastRef.current.slice(-(MAX_HISTORY - 1)), snapshot];
    futureRef.current = [];
  }, []);

  const undo = useCallback(
    (current: Snapshot, apply: (s: Snapshot) => void) => {
      if (pastRef.current.length === 0) return;
      const previous = pastRef.current[pastRef.current.length - 1];
      pastRef.current = pastRef.current.slice(0, -1);
      futureRef.current = [...futureRef.current, current];
      apply(previous);
    },
    [],
  );

  const redo = useCallback(
    (current: Snapshot, apply: (s: Snapshot) => void) => {
      if (futureRef.current.length === 0) return;
      const next = futureRef.current[futureRef.current.length - 1];
      futureRef.current = futureRef.current.slice(0, -1);
      pastRef.current = [...pastRef.current, current];
      apply(next);
    },
    [],
  );

  const canUndo = () => pastRef.current.length > 0;
  const canRedo = () => futureRef.current.length > 0;

  return { push, undo, redo, canUndo, canRedo };
}
