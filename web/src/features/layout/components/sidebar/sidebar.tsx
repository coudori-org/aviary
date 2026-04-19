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
import { SidebarWorkflows } from "./sidebar-workflows";
import { SidebarBulkBar } from "./sidebar-bulk-bar";
import { SidebarUser } from "./sidebar-user";
import { cn } from "@/lib/utils";

/**
 * Sidebar — translucent glass rail sitting on the aurora backdrop.
 *
 * backdrop-blur picks up the drifting colour. The thin gradient hairline
 * on the right edge keeps the rail visually distinct from the main pane
 * without introducing a hard line.
 */
export function Sidebar() {
  const { mode, groups, collapsed, viewMode } = useSidebar();
  const search = useSidebarSearch(groups);
  const isWorkflowMode = mode === "workflows";

  return (
    <aside
      className={cn(
        "relative flex shrink-0 flex-col transition-all duration-[320ms] ease-[cubic-bezier(0.16,1,0.3,1)]",
        "glass-deep",
        collapsed ? "w-16" : "w-[17.5rem]",
      )}
    >
      {/* Gradient right-edge hairline — aurora-A fade */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute right-0 top-0 h-full w-px bg-gradient-to-b from-aurora-violet/30 via-aurora-pink/20 to-transparent"
      />

      <SidebarBrand />

      {!collapsed && !isWorkflowMode && (
        <div className="pt-3">
          <SidebarSearch search={search} />
        </div>
      )}

      <div className="flex-1 overflow-y-auto pb-3">
        <SidebarNav />
        {isWorkflowMode ? (
          <SidebarWorkflows />
        ) : (
          <>
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
          </>
        )}
      </div>

      <SidebarUser />
    </aside>
  );
}
