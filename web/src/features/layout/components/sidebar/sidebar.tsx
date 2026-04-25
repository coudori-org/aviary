"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Bot,
  Workflow,
  Store,
  ChevronsLeft,
  ChevronsRight,
} from "@/components/icons";
import { AviaryLogo } from "@/components/brand/aviary-logo";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { routes } from "@/lib/constants/routes";

interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  match: (pathname: string) => boolean;
}

const NAV: NavItem[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    href: "/",
    icon: LayoutDashboard,
    match: (p) => p === "/",
  },
  {
    id: "agents",
    label: "Agents",
    href: routes.agents,
    icon: Bot,
    match: (p) => p.startsWith(routes.agents) || p.startsWith("/sessions"),
  },
  {
    id: "workflows",
    label: "Workflows",
    href: routes.workflows,
    icon: Workflow,
    match: (p) => p.startsWith(routes.workflows),
  },
  {
    id: "marketplace",
    label: "Marketplace",
    href: "/marketplace",
    icon: Store,
    match: (p) => p.startsWith("/marketplace"),
  },
];

export function Sidebar() {
  const { collapsed, toggleCollapsed } = useSidebar();
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "flex flex-col flex-shrink-0 bg-surface border-r border-border-subtle",
        "transition-[width] duration-panel ease-panel",
        collapsed ? "w-[56px]" : "w-[220px]"
      )}
      aria-label="Primary navigation"
    >
      <Brand collapsed={collapsed} />
      <nav className="flex-1 flex flex-col gap-[2px] px-2 py-[10px]">
        {NAV.map((item) => (
          <NavLink
            key={item.id}
            item={item}
            active={item.match(pathname)}
            collapsed={collapsed}
          />
        ))}
      </nav>
      <div className="p-2 border-t border-border-subtle">
        <button
          type="button"
          onClick={toggleCollapsed}
          className={cn(
            "flex items-center gap-[10px] h-[30px] w-full rounded-[7px] px-[10px]",
            "text-fg-tertiary hover:bg-hover hover:text-fg-secondary transition-colors duration-fast",
            collapsed ? "justify-center" : "justify-start"
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? <ChevronsRight size={15} /> : <ChevronsLeft size={15} />}
          {!collapsed && <span className="text-[12.5px]">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <Link
      href="/"
      className={cn(
        "flex items-center gap-[10px] h-[48px] px-[14px]",
        "border-b border-border-subtle",
        "text-fg-primary hover:bg-hover transition-colors duration-fast"
      )}
      aria-label="Aviary"
    >
      <AviaryLogo size={22} />
      {!collapsed && (
        <span className="t-h3 fg-primary leading-none tracking-[-0.01em]">
          Aviary
        </span>
      )}
    </Link>
  );
}

function NavLink({
  item,
  active,
  collapsed,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "relative flex items-center gap-[10px] h-[32px] rounded-[7px] px-[10px]",
        "text-[13px] transition-colors duration-fast",
        active
          ? "bg-active text-fg-primary font-medium"
          : "text-fg-secondary hover:bg-hover hover:text-fg-primary",
        collapsed ? "justify-center" : "justify-start"
      )}
      title={collapsed ? item.label : undefined}
      aria-current={active ? "page" : undefined}
    >
      {active && (
        <span
          className="absolute -left-2 top-2 bottom-2 w-[2px] rounded-[2px] bg-accent"
          aria-hidden
        />
      )}
      <Icon size={16} className="shrink-0" />
      {!collapsed && <span className="flex-1 text-left">{item.label}</span>}
    </Link>
  );
}
