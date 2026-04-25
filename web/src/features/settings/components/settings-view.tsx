"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Key, Settings as SettingsIcon, Sliders, User as UserIcon } from "@/components/icons";
import { LoadingState } from "@/components/feedback/loading-state";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { ProfilePanel } from "./profile-panel";
import { CredentialsPanel } from "./credentials-panel";
import { PreferencesPanel } from "./preferences-panel";
import { cn } from "@/lib/utils";

type Tab = "profile" | "credentials" | "preferences";

const TABS: Array<{ id: Tab; label: string; Icon: typeof UserIcon; hint: string }> = [
  { id: "profile", label: "Profile", Icon: UserIcon, hint: "Account identity" },
  { id: "credentials", label: "Credentials", Icon: Key, hint: "Vault-backed tokens" },
  { id: "preferences", label: "Preferences", Icon: Sliders, hint: "Theme & accents" },
];

function isTab(v: string | null): v is Tab {
  return v === "profile" || v === "credentials" || v === "preferences";
}

export function SettingsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tab: Tab = isTab(tabParam) ? tabParam : "profile";
  const { user, status } = useAuth();

  const setTab = React.useCallback(
    (next: Tab) => {
      const sp = new URLSearchParams(searchParams.toString());
      sp.set("tab", next);
      router.replace(`/settings?${sp.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  if (status === "loading") return <LoadingState fullHeight label="Loading settings…" />;

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-[1100px] px-8 py-6">
        <header className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-[8px] bg-hover text-fg-secondary">
            <SettingsIcon size={18} />
          </div>
          <div>
            <h1 className="t-h1 fg-primary">Settings</h1>
            <p className="t-small fg-tertiary">
              Manage your profile, credentials, and appearance.
            </p>
          </div>
        </header>

        <div className="grid gap-6 [grid-template-columns:200px_1fr]">
          <nav aria-label="Settings sections" className="flex flex-col gap-px">
            {TABS.map((t) => {
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group flex items-center gap-2 rounded-[6px] px-2 py-[7px] text-left",
                    "text-[12.5px] transition-colors duration-fast",
                    active
                      ? "bg-hover text-fg-primary font-medium"
                      : "text-fg-secondary hover:bg-hover/60 hover:text-fg-primary",
                  )}
                >
                  <t.Icon
                    size={13}
                    className={active ? "text-accent" : "text-fg-muted"}
                  />
                  <span className="flex-1">{t.label}</span>
                </button>
              );
            })}
          </nav>

          <section className="min-w-0">
            {tab === "profile" && <ProfilePanel user={user} />}
            {tab === "credentials" && <CredentialsPanel />}
            {tab === "preferences" && <PreferencesPanel />}
          </section>
        </div>
      </div>
    </div>
  );
}
