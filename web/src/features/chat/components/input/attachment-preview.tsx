"use client";

import { X, Loader2 } from "@/components/icons";
import type { PendingAttachment } from "@/types";

interface AttachmentPreviewProps {
  attachments: PendingAttachment[];
  onRemove: (localId: string) => void;
}

export function AttachmentPreview({ attachments, onRemove }: AttachmentPreviewProps) {
  if (attachments.length === 0) return null;

  return (
    <div className="flex gap-2 overflow-x-auto px-1 pb-2">
      {attachments.map((att) => (
        <div
          key={att.localId}
          className="group relative shrink-0 h-16 w-16 rounded-lg overflow-hidden border border-border bg-elevated"
        >
          <img
            src={att.preview}
            alt={att.file.name}
            className="h-full w-full object-cover"
          />
          {att.status === "uploading" && (
            <div className="absolute inset-0 flex items-center justify-center bg-canvas/60">
              <Loader2 size={16} className="animate-spin text-fg-muted" />
            </div>
          )}
          {att.status === "error" && (
            <div className="absolute inset-0 flex items-center justify-center bg-danger/20">
              <X size={14} className="text-danger" />
            </div>
          )}
          <button
            type="button"
            onClick={() => onRemove(att.localId)}
            className="absolute -right-1 -top-1 hidden group-hover:flex h-5 w-5 items-center justify-center rounded-full bg-elevated border border-border text-fg-muted hover:text-fg-primary transition-colors"
            aria-label={`Remove ${att.file.name}`}
          >
            <X size={10} />
          </button>
        </div>
      ))}
    </div>
  );
}
