"use client";

import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { http } from "@/lib/http";
import type { Session } from "@/types";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";

interface UseTitleEditorOptions {
  session: Session | null;
  patchSession: (patch: Partial<Session>) => void;
}

/**
 * useTitleEditor — encapsulates inline session-title editing.
 *
 * Owns: edit-mode flag, draft value, save-to-API, optimistic update,
 * keyboard handling. Exposes a stable API the header component renders against.
 */
export function useTitleEditor({ session, patchSession }: UseTitleEditorOptions) {
  const { updateSessionTitle } = useSidebar();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const startEditing = useCallback(() => {
    if (!session) return;
    setDraft(session.title || "");
    setIsEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, [session]);

  const save = useCallback(async () => {
    if (!session) return;
    setIsEditing(false);
    const trimmed = draft.trim();
    if (!trimmed || trimmed === session.title) return;

    const previousTitle = session.title;
    patchSession({ title: trimmed });
    updateSessionTitle(session.id, trimmed);

    try {
      await http.patch(`/sessions/${session.id}/title`, { title: trimmed });
    } catch {
      // Roll back optimistic update on failure
      patchSession({ title: previousTitle });
      updateSessionTitle(session.id, previousTitle || "");
    }
  }, [session, draft, patchSession, updateSessionTitle]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
    else if (e.key === "Escape") setIsEditing(false);
  }, []);

  const setAutoTitleFromMessage = useCallback(
    (content: string) => {
      if (!session || session.title) return;
      const firstLine = content.trim().split("\n")[0];
      const autoTitle = firstLine.length > 60 ? firstLine.slice(0, 57) + "…" : firstLine;
      patchSession({ title: autoTitle });
      updateSessionTitle(session.id, autoTitle);
    },
    [session, patchSession, updateSessionTitle],
  );

  return {
    isEditing,
    draft,
    setDraft,
    inputRef,
    startEditing,
    save,
    handleKeyDown,
    setAutoTitleFromMessage,
  };
}
