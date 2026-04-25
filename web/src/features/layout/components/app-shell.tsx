"use client";

import * as React from "react";
import { Sidebar } from "./sidebar/sidebar";
import { Header } from "./header/header";
import { CommandPaletteStub } from "./command-palette-stub";
import { NotificationsPanelStub } from "./notifications-panel-stub";
import { UserMenuStub } from "./user-menu-stub";
import { SessionStatusProvider } from "@/features/layout/providers/session-status-provider";
import { SidebarProvider } from "@/features/layout/providers/sidebar-provider";
import { PageHeaderProvider, usePageHeader } from "@/features/layout/providers/page-header-provider";

/**
 * AppShell — top-level frame for authenticated routes.
 *
 * Slate sidebar (220px nav-only) + dense header (48px) + scrollable main.
 * Per-agent session lists move into the agent detail's left panel; the
 * global sidebar carries primary nav only.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [notifOpen, setNotifOpen] = React.useState(false);
  const [userMenuOpen, setUserMenuOpen] = React.useState(false);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <SessionStatusProvider>
      <SidebarProvider>
        <PageHeaderProvider>
          <div className="flex h-screen overflow-hidden bg-canvas text-fg-primary">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <ShellHeader
                onOpenSearch={() => setSearchOpen(true)}
                onOpenNotifications={() => setNotifOpen((v) => !v)}
                onOpenUserMenu={() => setUserMenuOpen((v) => !v)}
                notifOpen={notifOpen}
                userMenuOpen={userMenuOpen}
              />
              <main className="flex-1 overflow-hidden">{children}</main>
            </div>
          </div>
          <CommandPaletteStub open={searchOpen} onClose={() => setSearchOpen(false)} />
          <NotificationsPanelStub open={notifOpen} onClose={() => setNotifOpen(false)} />
          <UserMenuStub open={userMenuOpen} onClose={() => setUserMenuOpen(false)} />
        </PageHeaderProvider>
      </SidebarProvider>
    </SessionStatusProvider>
  );
}

/**
 * Bridges the PageHeader slot into the Header component. Lives inside
 * the provider tree so it can read the slot.
 */
function ShellHeader(props: {
  onOpenSearch: () => void;
  onOpenNotifications: () => void;
  onOpenUserMenu: () => void;
  notifOpen: boolean;
  userMenuOpen: boolean;
}) {
  const { crumb } = usePageHeader();
  return <Header {...props} crumb={crumb} />;
}
