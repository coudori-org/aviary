"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid } from "@/components/icons";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

/**
 * SidebarNav — top-level navigation links (currently just "All Agents").
 * Designed to grow as new top-level sections are added.
 */
export function SidebarNav() {
  const pathname = usePathname();
  const { collapsed } = useSidebar();
  const isActive = pathname === routes.agents;

  return (
    <div className="px-3 pb-2">
      <Link
        href={routes.agents}
        className={cn(
          "flex items-center gap-2.5 rounded-sm px-3 py-2 type-nav transition-colors",
          isActive
            ? "bg-raised text-fg-primary"
            : "text-fg-muted hover:bg-white/[0.03] hover:text-fg-primary",
        )}
      >
        <LayoutGrid size={16} strokeWidth={1.75} />
        {!collapsed && "All Agents"}
      </Link>
    </div>
  );
}
