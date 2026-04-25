"use client";

import { useCallback, useState } from "react";
import { useChatSearchTargetId } from "@/features/chat/hooks/chat-search-context";
import { getUploadUrl } from "@/features/chat/lib/attachment-utils";
import { ImageLightbox } from "./image-lightbox";
import { cn } from "@/lib/utils";
import type { FileRef } from "@/types";

interface UserBubbleProps {
  content: string;
  showAvatar?: boolean;
  targetId: string;
  attachments?: FileRef[];
}

export function UserBubble({ content, showAvatar = true, targetId, attachments }: UserBubbleProps) {
  const activeTargetId = useChatSearchTargetId();
  const isActiveMatch = activeTargetId === targetId;
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);

  const openLightbox = useCallback((att: FileRef) => {
    setLightbox({ src: getUploadUrl(att.file_id), alt: att.filename });
  }, []);

  return (
    <div className="flex flex-row-reverse gap-3 group animate-fade-in">
      {showAvatar ? (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent type-small text-white">
          You
        </div>
      ) : (
        <div className="h-8 w-8 shrink-0" aria-hidden="true" />
      )}
      <div
        data-search-target={targetId}
        className={cn(
          "relative max-w-[70%] rounded-[12px_12px_2px_12px] bg-accent-soft border border-accent/40 transition-shadow",
          isActiveMatch && "ring-2 ring-accent/60 ring-offset-2 ring-offset-canvas",
        )}
      >
        <div className="px-4 py-3 type-body text-fg-primary">
          {attachments && attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {attachments.map((att) => (
                <button
                  key={att.file_id}
                  type="button"
                  onClick={() => openLightbox(att)}
                  className="block rounded-lg overflow-hidden border border-border-subtle hover:border-accent/40 transition-colors cursor-zoom-in"
                >
                  <img
                    src={getUploadUrl(att.file_id)}
                    alt={att.filename}
                    loading="lazy"
                    className="max-h-48 max-w-full object-contain rounded-lg"
                  />
                </button>
              ))}
            </div>
          )}
          {content && <div className="whitespace-pre-wrap break-words">{content}</div>}
        </div>
      </div>

      {lightbox && (
        <ImageLightbox
          src={lightbox.src}
          alt={lightbox.alt}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
