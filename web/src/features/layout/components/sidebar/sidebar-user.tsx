"use client";

import { LogOut } from "@/components/icons";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { useSidebar } from "@/features/layout/providers/sidebar-provider";

/**
 * SidebarUser — bottom user identity / sign-out section.
 *
 * Two layouts:
 *   - Collapsed: just an icon button (logout)
 *   - Expanded:  user name + ghost "Sign out" button
 */
export function SidebarUser() {
  const { user, logout } = useAuth();
  const { collapsed } = useSidebar();

  if (collapsed) {
    return (
      <div className="shrink-0 border-t border-border-subtle p-3">
        <button
          type="button"
          onClick={logout}
          className="flex h-8 w-full items-center justify-center rounded-sm text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors"
          title="Sign out"
          aria-label="Sign out"
        >
          <LogOut size={14} strokeWidth={1.75} />
        </button>
      </div>
    );
  }

  return (
    <div className="shrink-0 border-t border-border-subtle p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate type-caption text-fg-secondary">
            {user?.display_name || user?.email}
          </p>
        </div>
        <button
          type="button"
          onClick={logout}
          className="type-caption text-fg-muted hover:text-fg-primary transition-colors px-2 py-1 rounded-xs"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
