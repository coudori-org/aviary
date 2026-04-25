"use client";

import { useRef } from "react";
import { ImagePlus } from "@/components/icons";
import { ACCEPTED_IMAGE_TYPES } from "@/features/chat/lib/attachment-utils";

interface AttachmentButtonProps {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

export function AttachmentButton({ onFiles, disabled }: AttachmentButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(",")}
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length > 0) onFiles(files);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-fg-muted hover:text-fg-primary hover:bg-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Attach image"
      >
        <ImagePlus size={18} strokeWidth={1.75} />
      </button>
    </>
  );
}
