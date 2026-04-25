"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Send, Square, Upload } from "@/components/icons";
import { Kbd } from "@/components/ui/kbd";
import { MentionAutocomplete } from "./mention-autocomplete";
import { AttachmentPreview } from "./attachment-preview";
import { AttachmentButton } from "./attachment-button";
import { cn } from "@/lib/utils";
import type { FileRef, PendingAttachment } from "@/types";
import {
  validateImageFile,
  uploadFile,
  getUploadUrl,
  ACCEPTED_IMAGE_TYPES,
  MAX_ATTACHMENTS,
} from "@/features/chat/lib/attachment-utils";

interface ChatInputProps {
  onSend: (content: string, attachments?: FileRef[]) => void;
  onCancel?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  canCancel?: boolean;
  placeholder?: string;
  agentId?: string;
  visionEnabled?: boolean;
  restoreDraft?: { content: string; attachments?: FileRef[]; error?: string } | null;
  onDraftRestored?: () => void;
}

export function ChatInput({
  onSend,
  onCancel,
  disabled,
  isStreaming,
  canCancel,
  placeholder,
  agentId,
  visionEnabled,
  restoreDraft,
  onDraftRestored,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mentionOpenRef = useRef(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const dragDepthRef = useRef(0);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);

  const handleMentionOpenChange = useCallback((open: boolean) => {
    mentionOpenRef.current = open;
  }, []);

  const hasFiles = (e: React.DragEvent) =>
    Array.from(e.dataTransfer.types).includes("Files");

  // --- Attachment management ---

  const addFiles = useCallback(
    (files: File[]) => {
      if (!visionEnabled) return;

      const remaining = MAX_ATTACHMENTS - attachments.length;
      const toAdd = files.slice(0, remaining);

      for (const file of toAdd) {
        const error = validateImageFile(file);
        if (error) continue;

        const localId = crypto.randomUUID();
        const preview = URL.createObjectURL(file);
        const pending: PendingAttachment = {
          localId,
          file,
          preview,
          status: "uploading",
        };

        setAttachments((prev) => [...prev, pending]);

        uploadFile(file)
          .then((ref) => {
            setAttachments((prev) =>
              prev.map((a) =>
                a.localId === localId ? { ...a, status: "done", fileRef: ref } : a,
              ),
            );
          })
          .catch(() => {
            setAttachments((prev) =>
              prev.map((a) =>
                a.localId === localId ? { ...a, status: "error" } : a,
              ),
            );
          });
      }
    },
    [visionEnabled, attachments.length],
  );

  // Restore draft content after a rollback error
  useEffect(() => {
    if (!restoreDraft) return;
    setValue(restoreDraft.content);
    if (restoreDraft.attachments?.length && visionEnabled) {
      // Re-upload is not needed — file_ids are still valid in DB.
      // Create PendingAttachment entries with "done" status.
      const restored: PendingAttachment[] = restoreDraft.attachments.map((ref) => ({
        localId: crypto.randomUUID(),
        file: new File([], ref.filename),
        preview: getUploadUrl(ref.file_id),
        status: "done" as const,
        fileRef: ref,
      }));
      setAttachments(restored);
    }
    onDraftRestored?.();
    textareaRef.current?.focus();
  }, [restoreDraft, visionEnabled, onDraftRestored]);

  const removeAttachment = useCallback((localId: string) => {
    setAttachments((prev) => {
      const att = prev.find((a) => a.localId === localId);
      if (att) URL.revokeObjectURL(att.preview);
      return prev.filter((a) => a.localId !== localId);
    });
  }, []);

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      attachments.forEach((a) => URL.revokeObjectURL(a.preview));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Drag & drop ---

  const handleDragEnter = (e: React.DragEvent) => {
    if (!hasFiles(e) || !visionEnabled) return;
    e.preventDefault();
    dragDepthRef.current += 1;
    setIsDraggingFile(true);
  };

  const handleDragOver = (e: React.DragEvent) => {
    if (!hasFiles(e) || !visionEnabled) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!hasFiles(e)) return;
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDraggingFile(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepthRef.current = 0;
    setIsDraggingFile(false);
    if (!visionEnabled) return;

    const files = Array.from(e.dataTransfer.files).filter((f) =>
      ACCEPTED_IMAGE_TYPES.includes(f.type as (typeof ACCEPTED_IMAGE_TYPES)[number]),
    );
    if (files.length > 0) addFiles(files);
  };

  // --- Paste ---

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      if (!visionEnabled) return;
      const items = e.clipboardData?.items;
      if (!items) return;

      const imageFiles: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === "file" && ACCEPTED_IMAGE_TYPES.includes(item.type as (typeof ACCEPTED_IMAGE_TYPES)[number])) {
          const file = item.getAsFile();
          if (file) imageFiles.push(file);
        }
      }
      if (imageFiles.length > 0) {
        e.preventDefault();
        addFiles(imageFiles);
      }
    },
    [visionEnabled, addFiles],
  );

  // --- Auto-resize textarea ---

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const wasDisabledRef = useRef(!!disabled);
  useEffect(() => {
    if (wasDisabledRef.current && !disabled) {
      textareaRef.current?.focus();
    }
    wasDisabledRef.current = !!disabled;
  }, [disabled]);

  // --- Submit ---

  const doneAttachments = attachments.filter((a) => a.status === "done");
  const uploading = attachments.some((a) => a.status === "uploading");
  const canSend = (value.trim() || doneAttachments.length > 0) && !uploading;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = value.trim();
    if (!canSend || disabled) return;

    const refs = doneAttachments.map((a) => a.fileRef!);
    onSend(content, refs.length > 0 ? refs : undefined);
    setValue("");
    attachments.forEach((a) => URL.revokeObjectURL(a.preview));
    setAttachments([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (mentionOpenRef.current) return;
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className="relative"
    >
      <div
        className={cn(
          "flex flex-col rounded-xl bg-raised border border-border-subtle shadow-lg p-2",
          "transition-colors duration-200",
          !isDraggingFile && "focus-within:border-accent/50",
        )}
      >
        <AttachmentPreview attachments={attachments} onRemove={removeAttachment} />

        <div className="flex items-end gap-2">
          {visionEnabled && (
            <AttachmentButton
              onFiles={addFiles}
              disabled={attachments.length >= MAX_ATTACHMENTS}
            />
          )}

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={placeholder || "Send a message…"}
            className="max-h-[200px] min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 type-body text-fg-primary placeholder:text-fg-disabled focus:outline-none"
            rows={1}
          />

          {isStreaming ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={!canCancel}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-hover text-fg-secondary border border-border-subtle hover:bg-active transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label={canCancel ? "Stop generation" : "Waiting for server to acknowledge request…"}
            >
              <Square size={16} strokeWidth={2} fill="currentColor" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={disabled || !canSend}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent text-white hover:bg-accent/90 transition-colors duration-200 disabled:opacity-30 disabled:cursor-not-allowed"
              aria-label="Send message"
            >
              <Send size={16} strokeWidth={2} />
            </button>
          )}
        </div>
      </div>

      {visionEnabled && isDraggingFile && (
        <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-accent/60 bg-accent-soft animate-fade-in-fast">
          <Upload size={18} strokeWidth={1.75} className="text-accent" />
          <span className="type-caption-bold text-accent">Drop images to attach</span>
        </div>
      )}

      <MentionAutocomplete
        textareaRef={textareaRef}
        value={value}
        onChange={setValue}
        excludeAgentId={agentId}
        onOpenChange={handleMentionOpenChange}
      />

      <p className="mt-1.5 px-2 type-caption text-fg-disabled flex items-center gap-1.5">
        <Kbd>↵</Kbd>
        <span>to send,</span>
        <Kbd>⇧</Kbd>
        <Kbd>↵</Kbd>
        <span>for new line, type</span>
        <Kbd>@</Kbd>
        <span>to mention an agent.</span>
      </p>
    </form>
  );
}
