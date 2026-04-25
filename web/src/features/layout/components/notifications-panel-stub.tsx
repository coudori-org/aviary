"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface NotificationsPanelStubProps {
  open: boolean;
  onClose: () => void;
}

export function NotificationsPanelStub({ open, onClose }: NotificationsPanelStubProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80]" onClick={onClose} role="presentation">
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "absolute right-[14px] top-[52px] w-[360px] overflow-hidden",
          "rounded-[10px] border border-border bg-raised shadow-lg",
          "animate-slide-down"
        )}
        role="dialog"
        aria-label="Notifications"
      >
        <div className="flex items-center justify-between border-b border-border-subtle px-[14px] py-[10px]">
          <span className="t-h3 fg-primary">Notifications</span>
        </div>
        <div className="px-[14px] py-8 text-center text-[12.5px] text-fg-muted">
          Notification feed will appear here in Stage C4.
        </div>
      </div>
    </div>
  );
}
