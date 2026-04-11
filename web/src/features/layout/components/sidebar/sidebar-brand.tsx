"use client";

import Link from "next/link";
import { PanelLeftClose, PanelLeft } from "@/components/icons";
import { AviaryLogoMark } from "@/components/brand/aviary-logo";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { routes } from "@/lib/constants/routes";

/**
 * SidebarBrand — top header of the sidebar with logo + collapse toggle.
 * Pure presentation; data comes from useSidebar.
 */
export function SidebarBrand() {
  const { collapsed, toggleCollapsed } = useSidebar();

  return (
    <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/[0.06] px-4">
      {!collapsed && (
        <Link href={routes.agents} aria-label="Aviary home" className="flex items-center">
          <AviaryLogoMark size={28} />
        </Link>
      )}
      <button
        type="button"
        onClick={toggleCollapsed}
        className="flex h-7 w-7 items-center justify-center rounded-sm text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors"
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <PanelLeft size={14} strokeWidth={1.75} /> : <PanelLeftClose size={14} strokeWidth={1.75} />}
      </button>
    </div>
  );
}
