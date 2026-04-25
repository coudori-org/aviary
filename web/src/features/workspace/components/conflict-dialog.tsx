"use client";

import { useEffect } from "react";
import { cn } from "@/lib/utils";

interface ConflictDialogProps {
  path: string;
  code: "stale" | "exists";
  onOverwrite: () => void;
  onReload: () => void;
  onCancel: () => void;
}

export function ConflictDialog({
  path,
  code,
  onOverwrite,
  onReload,
  onCancel,
}: ConflictDialogProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const title =
    code === "stale"
      ? "File changed on disk"
      : "File already exists";
  const body =
    code === "stale"
      ? `${path} was modified since you opened it. Overwrite the changes, reload the latest version, or cancel?`
      : `${path} already exists. Overwrite it, reload the existing version, or cancel?`;

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
        <p className="mt-2 type-caption text-fg-muted break-words">{body}</p>
        <div className="mt-4 flex justify-end gap-2">
          <DialogButton onClick={onCancel}>Cancel</DialogButton>
          <DialogButton onClick={onReload}>Reload</DialogButton>
          <DialogButton onClick={onOverwrite} variant="danger">
            Overwrite
          </DialogButton>
        </div>
      </div>
    </div>
  );
}

function DialogButton({
  children,
  onClick,
  variant = "default",
}: {
  children: React.ReactNode;
  onClick: () => void;
  variant?: "default" | "danger";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-xs px-3 py-1.5 type-caption transition-colors",
        variant === "danger"
          ? "bg-danger/20 text-danger hover:bg-danger/30"
          : "bg-hover border border-border text-fg-primary hover:bg-active",
      )}
    >
      {children}
    </button>
  );
}
