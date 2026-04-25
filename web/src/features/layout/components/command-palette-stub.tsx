"use client";

import * as React from "react";
import { Search } from "@/components/icons";
import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";

export interface CommandPaletteStubProps {
  open: boolean;
  onClose: () => void;
}

export function CommandPaletteStub({ open, onClose }: CommandPaletteStubProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      className={cn(
        "fixed inset-0 z-[100] flex items-start justify-center pt-[100px]",
        "bg-overlay backdrop-blur-[2px] animate-fade-in-fast"
      )}
      role="presentation"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-[640px] max-w-[calc(100vw-32px)] overflow-hidden",
          "rounded-[12px] border border-border bg-raised shadow-xl",
          "animate-slide-up"
        )}
        role="dialog"
        aria-label="Command palette"
        aria-modal
      >
        <div className="flex items-center gap-[10px] border-b border-border-subtle px-[14px] py-3">
          <Search size={16} className="text-fg-tertiary" />
          <input
            autoFocus
            placeholder="Agents · Workflows · Sessions search…"
            className={cn(
              "flex-1 bg-transparent text-[14px] text-fg-primary outline-none",
              "placeholder:text-fg-muted"
            )}
            aria-label="Search query"
          />
          <Kbd>esc</Kbd>
        </div>
        <div className="px-7 py-10 text-center text-[13px] text-fg-muted">
          Search will land here in Stage C3 — agents, workflows, and full-text
          session message search.
        </div>
        <div
          className={cn(
            "flex items-center gap-3 border-t border-border-subtle px-[14px] py-2",
            "text-[11.5px] text-fg-muted"
          )}
        >
          <span className="inline-flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>
            navigate
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>↵</Kbd>
            select
          </span>
          <span className="ml-auto">Aviary Search</span>
        </div>
      </div>
    </div>
  );
}
