"use client";

import * as React from "react";
import { LogOut } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { cn } from "@/lib/utils";

export interface UserMenuStubProps {
  open: boolean;
  onClose: () => void;
}

export function UserMenuStub({ open, onClose }: UserMenuStubProps) {
  const { user, logout } = useAuth();
  if (!open) return null;

  const display = user?.display_name ?? user?.email ?? "Account";
  const initials = computeInitials(display);

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
        <div className="p-1 border-t border-border-subtle">
          <button
            type="button"
            onClick={() => {
              onClose();
              logout();
            }}
            className={cn(
              "flex w-full items-center gap-[10px] rounded-[6px] px-[10px] py-2",
              "text-left text-[12.5px] text-fg-secondary",
              "hover:bg-hover hover:text-fg-primary transition-colors duration-fast"
            )}
            role="menuitem"
          >
            <LogOut size={15} />
            Sign out
          </button>
        </div>
      </div>
    </div>
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
