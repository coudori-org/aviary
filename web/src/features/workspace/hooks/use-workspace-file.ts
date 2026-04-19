"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getFile, type FileContents } from "../lib/workspace-api";

interface UseWorkspaceFileResult {
  file: FileContents | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

/** Loads and re-loads a single file's contents. `path === null` clears state. */
export function useWorkspaceFile(
  sessionId: string,
  path: string | null,
): UseWorkspaceFileResult {
  const [file, setFile] = useState<FileContents | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generationRef = useRef(0);

  const load = useCallback(async () => {
    if (!path) return;
    const gen = ++generationRef.current;
    setLoading(true);
    setError(null);
    try {
      const contents = await getFile(sessionId, path);
      if (gen !== generationRef.current) return;
      setFile(contents);
    } catch (err) {
      if (gen !== generationRef.current) return;
      setError(err instanceof Error ? err.message : "Failed to load file");
      setFile(null);
    } finally {
      if (gen === generationRef.current) setLoading(false);
    }
  }, [sessionId, path]);

  useEffect(() => {
    if (path === null) {
      generationRef.current += 1;
      setFile(null);
      setError(null);
      setLoading(false);
      return;
    }
    void load();
  }, [path, load]);

  return { file, loading, error, reload: load };
}
