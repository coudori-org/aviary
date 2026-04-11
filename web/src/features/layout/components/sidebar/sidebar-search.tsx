"use client";

import { Search, X } from "@/components/icons";
import { Input } from "@/components/ui/input";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { cn } from "@/lib/utils";
import type { UseSidebarSearchResult } from "@/features/search/hooks/use-sidebar-search";

interface SidebarSearchProps {
  search: UseSidebarSearchResult;
}

/**
 * SidebarSearch — text input at the top of the sidebar.
 *
 * Hidden when the sidebar is collapsed (no room for an input — users can
 * still use the existing icon-only command-palette trigger from the
 * `SidebarSearchTrigger` component).
 */
export function SidebarSearch({ search }: SidebarSearchProps) {
  const { collapsed } = useSidebar();
  if (collapsed) return null;

  return (
    <div className="px-3 pb-2">
      <div className="relative">
        <Search
          size={12}
          strokeWidth={1.75}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-disabled"
        />
        <Input
          value={search.query}
          onChange={(e) => search.setQuery(e.target.value)}
          placeholder="Search…"
          className="h-8 pl-7 pr-7 type-caption"
        />
        {search.isActive && (
          <button
            type="button"
            onClick={search.clear}
            className={cn(
              "absolute right-1.5 top-1/2 -translate-y-1/2",
              "flex h-5 w-5 items-center justify-center rounded-xs",
              "text-fg-disabled hover:text-fg-primary hover:bg-white/[0.05] transition-colors",
            )}
            aria-label="Clear search"
          >
            <X size={11} strokeWidth={2} />
          </button>
        )}
      </div>
    </div>
  );
}
