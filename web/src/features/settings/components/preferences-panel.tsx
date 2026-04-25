"use client";

import * as React from "react";
import { Check, Moon, Sun } from "@/components/icons";
import { useTheme, type Theme } from "@/features/theme/theme-provider";
import { cn } from "@/lib/utils";

export function PreferencesPanel() {
  return (
    <div className="flex flex-col gap-4">
      <ThemeSection />
      <AccentSection />
    </div>
  );
}

function ThemeSection() {
  const { theme, setTheme } = useTheme();
  return (
    <Card>
      <h2 className="t-h2 fg-primary">Appearance</h2>
      <p className="mt-1 text-[12.5px] text-fg-secondary">
        Choose how Aviary looks on this device. The preference is saved in
        your browser.
      </p>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <ThemeOption
          active={theme === "dark"}
          onClick={() => setTheme("dark")}
          label="Dark"
          description="Default. Best for long focus sessions."
          Icon={Moon}
          tone="dark"
        />
        <ThemeOption
          active={theme === "light"}
          onClick={() => setTheme("light")}
          label="Light"
          description="Higher contrast for bright rooms."
          Icon={Sun}
          tone="light"
        />
      </div>
    </Card>
  );
}

function AccentSection() {
  return (
    <Card>
      <h2 className="t-h2 fg-primary">Accent</h2>
      <p className="mt-1 text-[12.5px] text-fg-secondary">
        Aviary ships with a single blue accent today. Per-user accents are
        coming soon.
      </p>
      <div className="mt-3 inline-flex items-center gap-2 rounded-[8px] border border-border-subtle bg-sunk px-3 py-[6px] text-[12px] text-fg-secondary">
        <span className="h-2.5 w-2.5 rounded-full bg-accent" /> Blue
        <span className="ml-1 text-fg-muted">·</span>
        <span className="text-fg-muted">Default</span>
      </div>
    </Card>
  );
}

interface ThemeOptionProps {
  active: boolean;
  onClick: () => void;
  label: string;
  description: string;
  Icon: typeof Moon;
  tone: Theme;
}

function ThemeOption({ active, onClick, label, description, Icon, tone }: ThemeOptionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "group relative flex flex-col items-start gap-2 rounded-[10px] border p-3 text-left",
        "transition-colors duration-fast",
        active
          ? "border-accent bg-accent-soft/40"
          : "border-border-subtle bg-raised hover:bg-hover",
      )}
    >
      <div className="flex w-full items-center gap-2">
        <div
          className={cn(
            "grid h-7 w-7 place-items-center rounded-[7px]",
            tone === "dark"
              ? "bg-[#0F1115] text-[#FAFAFA]"
              : "bg-[#FAF9F7] text-[#0F1115] border border-[#E5E1DA]",
          )}
        >
          <Icon size={14} />
        </div>
        <span className="t-body font-medium fg-primary">{label}</span>
        {active && <Check size={13} className="ml-auto text-accent" />}
      </div>
      <p className="text-[11.5px] text-fg-tertiary">{description}</p>
    </button>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border border-border-subtle bg-raised p-5">
      {children}
    </div>
  );
}
