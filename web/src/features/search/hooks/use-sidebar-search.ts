"use client";

import { useEffect, useMemo, useState } from "react";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import {
  searchApi,
  type MessageSearchHit,
  type MessageSearchResponse,
} from "@/features/search/api/search-api";
import type { SidebarAgentGroup } from "@/features/layout/providers/sidebar-provider";

/**
 * useSidebarSearch — owns the two-layer search experience for the sidebar.
 *
 * Layer 1 (instant, client-side):
 *   Filters the existing in-memory `groups` data by agent name + session
 *   title. Runs synchronously on every keystroke. Zero network cost.
 *
 * Layer 2 (debounced, backend):
 *   After 300ms of input stability, fires a single GET /search/messages
 *   call. Results are message-level full-text matches with snippets and
 *   the parent session info. Min query length is enforced to avoid
 *   triggering broad searches on 1-char inputs.
 *
 * The two layers are independent — layer 1 is always available, layer 2
 * fills in additional context. Both surface in the search dropdown UI.
 */

const DEBOUNCE_MS = 300;
const MIN_BACKEND_QUERY_LENGTH = 2;

export interface UseSidebarSearchResult {
  query: string;
  setQuery: (q: string) => void;
  clear: () => void;
  /** True iff query has any non-whitespace content */
  isActive: boolean;
  /** Sidebar groups filtered by query — pass to <SidebarSessions /> */
  filteredGroups: SidebarAgentGroup[];
  /** Backend full-text hits, may be loading */
  messageHits: MessageSearchHit[];
  messageHitsLoading: boolean;
  messageHitsError: string | null;
}

function filterGroups(groups: SidebarAgentGroup[], query: string): SidebarAgentGroup[] {
  const q = query.trim().toLowerCase();
  if (!q) return groups;

  return groups
    .map((group) => {
      const agentName = group.agent.name.toLowerCase();
      const agentSlug = group.agent.slug.toLowerCase();
      const agentDescription = (group.agent.description || "").toLowerCase();
      const agentMatches =
        agentName.includes(q) || agentSlug.includes(q) || agentDescription.includes(q);

      const matchedSessions = group.sessions.filter((s) =>
        (s.title || "").toLowerCase().includes(q),
      );

      // Show the whole group if the agent itself matches; otherwise only
      // include the group if at least one session title matches, and then
      // show only those matched sessions.
      if (agentMatches) {
        return group;
      }
      if (matchedSessions.length > 0) {
        return { ...group, sessions: matchedSessions };
      }
      return null;
    })
    .filter((g): g is SidebarAgentGroup => g !== null);
}

export function useSidebarSearch(groups: SidebarAgentGroup[]): UseSidebarSearchResult {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, DEBOUNCE_MS);

  const [messageHits, setMessageHits] = useState<MessageSearchHit[]>([]);
  const [messageHitsLoading, setMessageHitsLoading] = useState(false);
  const [messageHitsError, setMessageHitsError] = useState<string | null>(null);

  // Backend search runs only on debounced query AND only when long enough
  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (trimmed.length < MIN_BACKEND_QUERY_LENGTH) {
      setMessageHits([]);
      setMessageHitsError(null);
      setMessageHitsLoading(false);
      return;
    }

    let cancelled = false;
    setMessageHitsLoading(true);
    setMessageHitsError(null);

    searchApi
      .searchMessages(trimmed)
      .then((res: MessageSearchResponse) => {
        if (cancelled) return;
        setMessageHits(res.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setMessageHits([]);
        setMessageHitsError(err.message || "Search failed");
      })
      .finally(() => {
        if (!cancelled) setMessageHitsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  const filteredGroups = useMemo(() => filterGroups(groups, query), [groups, query]);

  const clear = () => setQuery("");
  const isActive = query.trim().length > 0;

  return {
    query,
    setQuery,
    clear,
    isActive,
    filteredGroups,
    messageHits,
    messageHitsLoading,
    messageHitsError,
  };
}
