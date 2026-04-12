"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, GitBranch } from "@/components/icons";
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

function NavLink({ href, active, collapsed, icon, label }: NavLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 rounded-sm px-3 py-2 type-nav transition-colors",
        active
          ? "bg-raised text-fg-primary"
          : "text-fg-muted hover:bg-white/[0.03] hover:text-fg-primary",
      )}
    >
      {icon}
      {!collapsed && label}
    </Link>
  );
}

export function SidebarNav() {
  const pathname = usePathname();
  const { collapsed } = useSidebar();

  return (
    <div className="flex flex-col gap-0.5 px-3 pb-2">
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
    </div>
  );
}
