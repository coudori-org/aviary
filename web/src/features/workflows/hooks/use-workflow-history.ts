import { useCallback, useRef, useState } from "react";

interface Snapshot {
  nodes: unknown[];
  edges: unknown[];
}

const MAX_HISTORY = 50;

/**
 * Standalone undo/redo stack. Callers own nodes/edges state and call
 * push/undo/redo imperatively; the hook triggers its own re-render on
 * every mutation so `canUndo`/`canRedo` stay fresh without a manual bump.
 */
export function useWorkflowHistory() {
  const pastRef = useRef<Snapshot[]>([]);
  const futureRef = useRef<Snapshot[]>([]);
  const [, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  const push = useCallback((snapshot: Snapshot) => {
    pastRef.current = [...pastRef.current.slice(-(MAX_HISTORY - 1)), snapshot];
    futureRef.current = [];
    bump();
  }, [bump]);

  const undo = useCallback(
    (current: Snapshot, apply: (s: Snapshot) => void) => {
      if (pastRef.current.length === 0) return;
      const previous = pastRef.current[pastRef.current.length - 1];
      pastRef.current = pastRef.current.slice(0, -1);
      futureRef.current = [...futureRef.current, current];
      apply(previous);
      bump();
    },
    [bump],
  );

  const redo = useCallback(
    (current: Snapshot, apply: (s: Snapshot) => void) => {
      if (futureRef.current.length === 0) return;
      const next = futureRef.current[futureRef.current.length - 1];
      futureRef.current = futureRef.current.slice(0, -1);
      pastRef.current = [...pastRef.current, current];
      apply(next);
      bump();
    },
    [bump],
  );

  return {
    push,
    undo,
    redo,
    canUndo: pastRef.current.length > 0,
    canRedo: futureRef.current.length > 0,
  };
}
