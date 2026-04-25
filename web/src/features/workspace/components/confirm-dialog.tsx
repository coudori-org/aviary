"use client";

import { useEffect } from "react";
import { cn } from "@/lib/utils";

interface ConfirmDialogProps {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
  thirdAction?: {
    label: string;
    onClick: () => void;
  };
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  danger,
  thirdAction,
}: ConfirmDialogProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Enter") {
        if (e.isComposing || e.keyCode === 229) return;
        onConfirm();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, onConfirm]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay animate-fade-in-fast"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-[min(420px,90vw)] rounded-md border border-border bg-popover p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="type-body font-semibold text-fg-primary">{title}</h2>
        <p className="mt-2 type-caption text-fg-muted break-words whitespace-pre-wrap">{body}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xs bg-hover border border-border px-3 py-1.5 type-caption text-fg-primary hover:bg-active"
          >
            {cancelLabel}
          </button>
          {thirdAction && (
            <button
              type="button"
              onClick={thirdAction.onClick}
              className="rounded-xs bg-hover border border-border px-3 py-1.5 type-caption text-fg-primary hover:bg-active"
            >
              {thirdAction.label}
            </button>
          )}
          <button
            type="button"
            onClick={onConfirm}
            className={cn(
              "rounded-xs px-3 py-1.5 type-caption transition-colors",
              danger
                ? "bg-danger/20 text-danger hover:bg-danger/30"
                : "bg-info/20 text-info hover:bg-info/30",
            )}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
