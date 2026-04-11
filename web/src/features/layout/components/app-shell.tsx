"use client";

import { Sidebar } from "./sidebar/sidebar";
import { AgentStatusProvider } from "@/features/layout/providers/agent-status-provider";
import { SessionStatusProvider } from "@/features/layout/providers/session-status-provider";
import { SidebarProvider } from "@/features/layout/providers/sidebar-provider";

/**
 * AppShell — top-level frame for authenticated routes.
 *
 * Composition order matters: status providers must wrap SidebarProvider
 * because the latter calls useSetAgentIds / useSetSessionIds.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AgentStatusProvider>
      <SessionStatusProvider>
        <SidebarProvider>
          <div className="flex h-screen overflow-hidden bg-canvas">
            <Sidebar />
            <main className="flex-1 overflow-hidden">{children}</main>
          </div>
        </SidebarProvider>
      </SessionStatusProvider>
    </AgentStatusProvider>
  );
}
