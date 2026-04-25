"use client";

import * as React from "react";
import Link from "next/link";
import { LogOut, Moon, Settings as SettingsIcon, Sun } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { useTheme } from "@/features/theme/theme-provider";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";

export interface UserMenuStubProps {
  open: boolean;
  onClose: () => void;
}

export function UserMenuStub({ open, onClose }: UserMenuStubProps) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  if (!open) return null;

  const display = user?.display_name ?? user?.email ?? "Account";
  const initials = computeInitials(display);
  const ThemeIcon = theme === "dark" ? Sun : Moon;

  return (
    <div className="fixed inset-0 z-[80]" onClick={onClose} role="presentation">
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "absolute right-[14px] top-[52px] w-[260px] overflow-hidden",
          "rounded-[10px] border border-border bg-raised shadow-lg",
          "animate-slide-down"
        )}
        role="menu"
        aria-label="User menu"
      >
        <div className="flex items-center gap-[10px] border-b border-border-subtle p-[14px]">
          <Avatar tone="blue" size="lg" shape="circle">
            {initials}
          </Avatar>
          <div className="min-w-0 flex-1">
            <div className="t-h3 fg-primary truncate">{display}</div>
            {user?.email && (
              <div className="t-small fg-tertiary truncate">{user.email}</div>
            )}
          </div>
        </div>
        <div className="p-1">
          <MenuLink
            href={routes.settings}
            onClick={onClose}
            icon={<SettingsIcon size={15} />}
            label="Settings"
          />
          <MenuButton
            onClick={() => {
              toggleTheme();
            }}
            icon={<ThemeIcon size={15} />}
            label={theme === "dark" ? "Switch to light" : "Switch to dark"}
          />
        </div>
        <div className="border-t border-border-subtle p-1">
          <MenuButton
            onClick={() => {
              onClose();
              logout();
            }}
            icon={<LogOut size={15} />}
            label="Sign out"
          />
        </div>
      </div>
    </div>
  );
}

function MenuLink({
  href,
  onClick,
  icon,
  label,
}: {
  href: string;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      role="menuitem"
      className={cn(
        "flex w-full items-center gap-[10px] rounded-[6px] px-[10px] py-2",
        "text-left text-[12.5px] text-fg-secondary",
        "hover:bg-hover hover:text-fg-primary transition-colors duration-fast"
      )}
    >
      {icon}
      {label}
    </Link>
  );
}

function MenuButton({
  onClick,
  icon,
  label,
}: {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="menuitem"
      className={cn(
        "flex w-full items-center gap-[10px] rounded-[6px] px-[10px] py-2",
        "text-left text-[12.5px] text-fg-secondary",
        "hover:bg-hover hover:text-fg-primary transition-colors duration-fast"
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function computeInitials(source: string): string {
  const trimmed = source.trim();
  if (!trimmed) return "";
  if (trimmed.includes("@")) {
    return trimmed.split("@")[0].slice(0, 2).toUpperCase();
  }
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
