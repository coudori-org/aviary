"use client";

import { Sidebar } from "./sidebar/sidebar";
import { SessionStatusProvider } from "@/features/layout/providers/session-status-provider";
import { SidebarProvider } from "@/features/layout/providers/sidebar-provider";

/**
 * AppShell — top-level frame for authenticated routes.
 *
 * Canvas is intentionally transparent: the global <AuroraBackdrop> in
 * RootLayout paints the deep-navy base plus drifting colour behind
 * everything. The sidebar + main content are glass panes that pick up
 * the bleed through backdrop-blur.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SessionStatusProvider>
      <SidebarProvider>
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-hidden">{children}</main>
        </div>
      </SidebarProvider>
    </SessionStatusProvider>
  );
}
