"use client";

import * as React from "react";
import { Search, Bell, User as UserIcon } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";
import { useAuth } from "@/features/auth/providers/auth-provider";

export interface HeaderProps {
  onOpenSearch: () => void;
  onOpenNotifications: () => void;
  onOpenUserMenu: () => void;
  notifOpen: boolean;
  userMenuOpen: boolean;
  hasUnreadNotifications?: boolean;
  /** Optional left slot for breadcrumbs / page titles. */
  crumb?: React.ReactNode;
}

export function Header({
  onOpenSearch,
  onOpenNotifications,
  onOpenUserMenu,
  notifOpen,
  userMenuOpen,
  hasUnreadNotifications = false,
  crumb,
}: HeaderProps) {
  return (
    <header
      className={cn(
        "relative z-[3] flex h-[48px] flex-shrink-0 items-center gap-3",
        "border-b border-border-subtle bg-canvas",
        "pl-[18px] pr-[14px]"
      )}
    >
      <div className="flex flex-1 items-center gap-2 min-w-0">{crumb}</div>

      <div className="flex items-center gap-[6px]">
        <button
          type="button"
          onClick={onOpenSearch}
          className={cn(
            "flex h-[30px] min-w-[200px] items-center gap-2 rounded-[7px]",
            "border border-border bg-sunk px-[10px]",
            "text-[12.5px] text-fg-muted",
            "hover:bg-hover hover:border-border-strong transition-colors duration-fast"
          )}
          aria-label="Open search (⌘K)"
        >
          <Search size={14} />
          <span className="flex-1 text-left">Search…</span>
          <Kbd>⌘</Kbd>
          <Kbd>K</Kbd>
        </button>

        <button
          type="button"
          onClick={onOpenNotifications}
          className={cn(
            "relative inline-flex h-[30px] w-[30px] items-center justify-center rounded-[7px]",
            "text-fg-secondary hover:bg-hover hover:text-fg-primary transition-colors duration-fast",
            notifOpen && "bg-hover text-fg-primary"
          )}
          aria-label="Notifications"
          aria-expanded={notifOpen}
        >
          <Bell size={16} />
          {hasUnreadNotifications && (
            <span
              className={cn(
                "absolute right-[6px] top-[6px] h-[7px] w-[7px] rounded-full bg-status-warn",
                "border-2 border-canvas"
              )}
              aria-hidden
            />
          )}
        </button>

        <UserButton open={userMenuOpen} onClick={onOpenUserMenu} />
      </div>
    </header>
  );
}

function UserButton({ open, onClick }: { open: boolean; onClick: () => void }) {
  const { user } = useAuth();
  const initials = computeInitials(user?.display_name ?? user?.email ?? "");
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex h-[32px] w-[32px] items-center justify-center rounded-full p-[2px]",
        "transition-colors duration-fast",
        open ? "bg-hover" : "hover:bg-hover"
      )}
      title={user?.display_name ?? user?.email ?? "Account"}
      aria-label="Open user menu"
      aria-expanded={open}
    >
      {initials ? (
        <Avatar tone="blue" size="md" shape="circle" className="!text-[10.5px]">
          {initials}
        </Avatar>
      ) : (
        <span className="inline-flex h-[26px] w-[26px] items-center justify-center rounded-full bg-hover text-fg-tertiary">
          <UserIcon size={14} />
        </span>
      )}
    </button>
  );
}

function computeInitials(source: string): string {
  const trimmed = source.trim();
  if (!trimmed) return "";
  if (trimmed.includes("@")) {
    const local = trimmed.split("@")[0];
    return local.slice(0, 2).toUpperCase();
  }
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
