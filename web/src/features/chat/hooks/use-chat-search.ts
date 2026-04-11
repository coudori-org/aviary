"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { http } from "@/lib/http";
import type { Message } from "@/types";

interface UseChatSearchOptions {
  sessionId: string;
  messages: Message[];
  hasMore: boolean;
  loadEarlier: () => Promise<void>;
}

interface BackendMatch {
  message_id: string;
  target_id: string;
}

export interface ChatSearchState {
  open: boolean;
  query: string;
  matchCount: number;
  currentIdx: number;
  currentTargetId: string | null;
  searching: boolean;
  navigating: boolean;
  setQuery: (q: string) => void;
  next: () => void;
  prev: () => void;
  openSearch: () => void;
  closeSearch: () => void;
}

const SEARCH_DEBOUNCE_MS = 250;
const MIN_QUERY_LENGTH = 2;

/**
 * useChatSearch — block-level in-chat search backed by the session
 * search endpoint, lazy-loading older history only when navigation
 * actually walks into a not-yet-rendered match.
 *
 * The backend returns one `(message_id, target_id)` per matching block;
 * each `target_id` matches the `data-search-target` attribute the
 * frontend paints on the corresponding bubble. Navigation just walks
 * that list — when the active match's message isn't in the rendered
 * window, an effect loops `loadEarlier()` until it lands.
 */
export function useChatSearch({
  sessionId,
  messages,
  hasMore,
  loadEarlier,
}: UseChatSearchOptions): ChatSearchState {
  const [open, setOpen] = useState(false);
  const [query, setQueryState] = useState("");
  const [matches, setMatches] = useState<BackendMatch[]>([]);
  const [currentIdx, setCurrentIdx] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [navigating, setNavigating] = useState(false);

  const hasMoreRef = useRef(hasMore);
  const loadEarlierRef = useRef(loadEarlier);
  useEffect(() => {
    hasMoreRef.current = hasMore;
    loadEarlierRef.current = loadEarlier;
  });

  const openSearch = useCallback(() => setOpen(true), []);
  const closeSearch = useCallback(() => {
    setOpen(false);
    setQueryState("");
    setMatches([]);
    setCurrentIdx(-1);
    setSearching(false);
    setNavigating(false);
  }, []);

  const setQuery = useCallback((q: string) => setQueryState(q), []);

  // Debounced backend fetch.
  useEffect(() => {
    const trimmed = query.trim();
    if (!open || trimmed.length < MIN_QUERY_LENGTH) {
      setMatches([]);
      setCurrentIdx(-1);
      setSearching(false);
      return;
    }

    let cancelled = false;
    setSearching(true);
    const handle = setTimeout(async () => {
      try {
        const data = await http.get<{ matches: BackendMatch[] }>(
          `/sessions/${sessionId}/search?q=${encodeURIComponent(trimmed)}`,
        );
        if (cancelled) return;
        setMatches(data.matches);
        setCurrentIdx(data.matches.length > 0 ? 0 : -1);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, open, sessionId]);

  const currentMatch =
    currentIdx >= 0 && currentIdx < matches.length ? matches[currentIdx] : null;

  // Pull older history until the active match's message lands.
  useEffect(() => {
    if (!currentMatch) {
      setNavigating(false);
      return;
    }
    if (messages.some((m) => m.id === currentMatch.message_id)) {
      setNavigating(false);
      return;
    }
    if (!hasMoreRef.current) {
      setNavigating(false);
      return;
    }
    setNavigating(true);
    void loadEarlierRef.current();
  }, [currentMatch, messages, hasMore]);

  const next = useCallback(() => {
    if (matches.length === 0) return;
    setCurrentIdx((idx) => (idx + 1) % matches.length);
  }, [matches]);

  const prev = useCallback(() => {
    if (matches.length === 0) return;
    setCurrentIdx((idx) => (idx <= 0 ? matches.length - 1 : idx - 1));
  }, [matches]);

  return {
    open,
    query,
    matchCount: matches.length,
    currentIdx,
    currentTargetId: currentMatch?.target_id ?? null,
    searching,
    navigating,
    setQuery,
    next,
    prev,
    openSearch,
    closeSearch,
  };
}
