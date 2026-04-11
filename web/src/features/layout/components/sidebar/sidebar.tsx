"use client";

import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { useSidebarSearch } from "@/features/search/hooks/use-sidebar-search";
import { SearchResults } from "@/features/search/components/search-results";
import { SidebarBrand } from "./sidebar-brand";
import { SidebarSearch } from "./sidebar-search";
import { SidebarViewToggle } from "./sidebar-view-toggle";
import { SidebarNav } from "./sidebar-nav";
import { SidebarSessions } from "./sidebar-sessions";
import { SidebarSessionsByDate } from "./sidebar-sessions-by-date";
import { SidebarBulkBar } from "./sidebar-bulk-bar";
import { SidebarUser } from "./sidebar-user";
import { cn } from "@/lib/utils";

/**
 * Sidebar — assembles brand, search, nav, sessions, and user sections.
 *
 * The search hook lives at this level so it can both:
 *   - Filter the in-memory groups (instant, used by SidebarSessions)
 *   - Trigger debounced backend message search (results in SearchResults)
 *
 * View mode (by-agent vs by-date) is controlled by SidebarProvider and
 * persisted to localStorage. SidebarViewToggle flips between the two
 * dedicated rendering components.
 */
export function Sidebar() {
  const { groups, collapsed, viewMode } = useSidebar();
  const search = useSidebarSearch(groups);

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-white/[0.06] bg-elevated transition-all duration-200",
        collapsed ? "w-16" : "w-[17.5rem]",
      )}
    >
      <SidebarBrand />

      {!collapsed && (
        <div className="pt-3">
          <SidebarSearch search={search} />
        </div>
      )}

      <div className="flex-1 overflow-y-auto pb-3">
        <SidebarNav />
        <SidebarViewToggle />
        <SidebarBulkBar />
        {viewMode === "agent" ? (
          <SidebarSessions
            groups={search.filteredGroups}
            searchActive={search.isActive}
          />
        ) : (
          <SidebarSessionsByDate
            groups={search.filteredGroups}
            searchActive={search.isActive}
          />
        )}
        {search.isActive && (
          <SearchResults
            hits={search.messageHits}
            loading={search.messageHitsLoading}
            error={search.messageHitsError}
            query={search.query}
            onResultClick={search.clear}
          />
        )}
      </div>

      <SidebarUser />
    </aside>
  );
}
