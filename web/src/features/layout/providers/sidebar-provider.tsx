"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import { http } from "@/lib/http";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { useSetSessionIds } from "./session-status-provider";
import type { Agent, Session } from "@/types";

export interface SidebarAgentGroup {
  agent: Agent;
  sessions: Session[];
}

export type SidebarViewMode = "agent" | "date";

const VIEW_MODE_STORAGE_KEY = "aviary_sidebar_view_mode";
const COLLAPSED_AGENTS_STORAGE_KEY = "aviary_collapsed_agents";

interface SidebarContextValue {
  groups: SidebarAgentGroup[];
  loading: boolean;
  collapsed: boolean;
  toggleCollapsed: () => void;
  viewMode: SidebarViewMode;
  setViewMode: (mode: SidebarViewMode) => void;
  /** Set of agent IDs whose nested session lists are collapsed in
   *  By Agent view. Persisted to localStorage. */
  collapsedAgents: Set<string>;
  toggleAgentCollapsed: (agentId: string) => void;
  refresh: () => Promise<void>;
  updateSessionTitle: (sessionId: string, title: string) => void;
  deleteSession: (sessionId: string) => Promise<void>;
  // --- Bulk selection (SIDE-5) ---
  /** Set of currently multi-selected session ids. */
  selectedSessionIds: Set<string>;
  /** Register the currently visible session ids in their rendered order
   *  so range-select (shift+click) can compute a contiguous span. Each
   *  active session list view calls this from an effect. */
  setVisibleSessionIds: (ids: string[]) => void;
  /** Plain toggle on a single session + set as the shift-range anchor. */
  toggleSessionSelection: (id: string) => void;
  /** Shift-click behavior: if an anchor exists, select every id between
   *  the anchor and `id` in the current visible order; otherwise toggle. */
  shiftSelectSession: (id: string) => void;
  clearSessionSelection: () => void;
  /** Bulk delete all currently selected sessions. */
  deleteSelectedSessions: () => Promise<void>;
}

// Note: deleted-at-bottom + user-defined ordering now lives in
// `features/layout/lib/sidebar-ordering.ts` (orderGroupsByPreference).
// The provider only owns raw data and persistence — sorting is a view concern.

const SidebarContext = createContext<SidebarContextValue | null>(null);

/**
 * SidebarProvider — owns the data for the sidebar (agents + their active sessions).
 *
 * Lifted out of the AppShell component so that:
 *   1. Page-level components (e.g. ChatView) can call updateSessionTitle()
 *      without prop drilling.
 *   2. Polling provider feeds (agent / session status) get clean ID lists.
 *   3. The visual AppShell can stay purely presentational.
 */
export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const [groups, setGroups] = useState<SidebarAgentGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [viewMode, setViewModeState] = useState<SidebarViewMode>("agent");
  const [collapsedAgents, setCollapsedAgents] = useState<Set<string>>(() => new Set());
  const setSessionIds = useSetSessionIds();

  // Read persisted preferences after mount (avoid SSR localStorage access)
  useEffect(() => {
    if (typeof window === "undefined") return;

    const storedMode = window.localStorage.getItem(VIEW_MODE_STORAGE_KEY);
    if (storedMode === "date" || storedMode === "agent") {
      setViewModeState(storedMode);
    }

    const storedCollapsed = window.localStorage.getItem(COLLAPSED_AGENTS_STORAGE_KEY);
    if (storedCollapsed) {
      try {
        const parsed = JSON.parse(storedCollapsed);
        if (Array.isArray(parsed)) {
          setCollapsedAgents(new Set(parsed.filter((id): id is string => typeof id === "string")));
        }
      } catch {
        // Corrupt JSON — ignore and start fresh. Will be overwritten on first toggle.
      }
    }
  }, []);

  const setViewMode = useCallback((mode: SidebarViewMode) => {
    setViewModeState(mode);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
    }
  }, []);

  const toggleAgentCollapsed = useCallback((agentId: string) => {
    setCollapsedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(
          COLLAPSED_AGENTS_STORAGE_KEY,
          JSON.stringify(Array.from(next)),
        );
      }
      return next;
    });
  }, []);

  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const { items: agents } = await http.get<{ items: Agent[] }>("/agents");
      const withSessions = await Promise.all(
        agents.map(async (agent) => {
          const { items } = await http.get<{ items: Session[] }>(
            `/agents/${agent.id}/sessions`,
          );
          return { agent, sessions: items.filter((s) => s.status === "active") };
        }),
      );
      setGroups(withSessions);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Refresh sidebar when entering a session URL (a session may have been
  // just created on a different page; this catches it without prop drilling).
  useEffect(() => {
    if (pathname.startsWith("/sessions/")) {
      refresh();
    }
  }, [pathname, refresh]);

  useEffect(() => {
    setSessionIds(groups.flatMap((g) => g.sessions).map((s) => s.id));
  }, [groups, setSessionIds]);

  const updateSessionTitle = useCallback((sessionId: string, title: string) => {
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        sessions: g.sessions.map((s) => (s.id === sessionId ? { ...s, title } : s)),
      })),
    );
  }, []);

  const deleteSession = useCallback(async (sessionId: string) => {
    await http.delete(`/sessions/${sessionId}`);
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        sessions: g.sessions.filter((s) => s.id !== sessionId),
      })),
    );
  }, []);

  // --- Bulk selection state (SIDE-5) ---
  const [selectedSessionIds, setSelectedSessionIds] = useState<Set<string>>(
    () => new Set(),
  );
  // Ref holds the current visible-session ordering pushed from whichever
  // session list view is mounted. Used for shift-range selection.
  const visibleSessionIdsRef = useRef<string[]>([]);
  const anchorRef = useRef<string | null>(null);

  const setVisibleSessionIds = useCallback((ids: string[]) => {
    visibleSessionIdsRef.current = ids;
  }, []);

  const toggleSessionSelection = useCallback((id: string) => {
    setSelectedSessionIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    anchorRef.current = id;
  }, []);

  const shiftSelectSession = useCallback((id: string) => {
    const ordered = visibleSessionIdsRef.current;
    const anchor = anchorRef.current;
    if (!anchor || !ordered.includes(anchor)) {
      // No usable anchor — fall back to single toggle.
      setSelectedSessionIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      anchorRef.current = id;
      return;
    }
    const a = ordered.indexOf(anchor);
    const b = ordered.indexOf(id);
    if (b === -1) return;
    const [lo, hi] = a < b ? [a, b] : [b, a];
    const rangeIds = ordered.slice(lo, hi + 1);
    setSelectedSessionIds((prev) => {
      const next = new Set(prev);
      for (const rid of rangeIds) next.add(rid);
      return next;
    });
    // Anchor stays put so subsequent shift-clicks keep extending from it.
  }, []);

  const clearSessionSelection = useCallback(() => {
    setSelectedSessionIds(new Set());
    anchorRef.current = null;
  }, []);

  const deleteSelectedSessions = useCallback(async () => {
    const ids = Array.from(selectedSessionIds);
    if (ids.length === 0) return;
    await Promise.all(ids.map((id) => http.delete(`/sessions/${id}`)));
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        sessions: g.sessions.filter((s) => !selectedSessionIds.has(s.id)),
      })),
    );
    setSelectedSessionIds(new Set());
    anchorRef.current = null;
  }, [selectedSessionIds]);

  // Clear any stale selection on route change — navigating to a chat
  // implicitly ends a bulk-edit flow.
  useEffect(() => {
    if (selectedSessionIds.size > 0) {
      setSelectedSessionIds(new Set());
      anchorRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), []);

  return (
    <SidebarContext.Provider
      value={{
        groups,
        loading,
        collapsed,
        toggleCollapsed,
        viewMode,
        setViewMode,
        collapsedAgents,
        toggleAgentCollapsed,
        refresh,
        updateSessionTitle,
        deleteSession,
        selectedSessionIds,
        setVisibleSessionIds,
        toggleSessionSelection,
        shiftSelectSession,
        clearSessionSelection,
        deleteSelectedSessions,
      }}
    >
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error("useSidebar must be used within SidebarProvider");
  return ctx;
}
