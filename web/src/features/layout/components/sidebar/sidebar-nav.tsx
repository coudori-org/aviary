"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, GitBranch, Store } from "@/components/icons";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

interface NavLinkProps {
  href: string;
  active: boolean;
  collapsed: boolean;
  icon: React.ReactNode;
  label: string;
}

/**
 * NavLink — active state gets a 2px accent left rail; inactive stays
 * neutral with a subtle hover.
 */
function NavLink({ href, active, collapsed, icon, label }: NavLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        "relative flex items-center gap-2.5 rounded-sm px-3 py-2 type-nav",
        "transition-colors duration-200",
        active
          ? "text-fg-primary"
          : "text-fg-muted hover:bg-hover hover:text-fg-primary",
      )}
    >
      {active && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1.5 bottom-1.5 w-0.5 bg-accent"
        />
      )}
      {icon}
      {!collapsed && label}
    </Link>
  );
}

export function SidebarNav() {
  const pathname = usePathname();
  const { collapsed } = useSidebar();

  return (
    <div className="flex flex-col gap-0.5 px-3 pb-2 pt-2">
      <NavLink
        href={routes.agents}
        active={pathname === routes.agents}
        collapsed={collapsed}
        icon={<LayoutGrid size={16} strokeWidth={1.75} />}
        label="All Agents"
      />
      <NavLink
        href={routes.workflows}
        active={pathname.startsWith(routes.workflows)}
        collapsed={collapsed}
        icon={<GitBranch size={16} strokeWidth={1.75} />}
        label="Workflows"
      />
      <NavLink
        href={routes.marketplace}
        active={pathname.startsWith(routes.marketplace)}
        collapsed={collapsed}
        icon={<Store size={16} strokeWidth={1.75} />}
        label="Marketplace"
      />
    </div>
  );
}
