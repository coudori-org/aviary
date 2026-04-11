"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Send, Square, Upload } from "@/components/icons";
import { Kbd } from "@/components/ui/kbd";
import { MentionAutocomplete } from "./mention-autocomplete";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (content: string) => void;
  onCancel?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  agentId?: string;
}

/**
 * ChatInput — auto-resizing textarea with send/cancel button.
 *
 * Send button is replaced by a square "stop" button while streaming.
 * MentionAutocomplete handles its own keyboard events when open.
 */
export function ChatInput({
  onSend,
  onCancel,
  disabled,
  isStreaming,
  placeholder,
  agentId,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mentionOpenRef = useRef(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [showDropFeedback, setShowDropFeedback] = useState(false);
  // Nested children flip dragenter/leave events — track the depth so
  // the overlay only disappears when the pointer actually leaves the
  // form root, not when moving between its children.
  const dragDepthRef = useRef(0);

  const handleMentionOpenChange = useCallback((open: boolean) => {
    mentionOpenRef.current = open;
  }, []);

  const hasFiles = (e: React.DragEvent) =>
    Array.from(e.dataTransfer.types).includes("Files");

  const handleDragEnter = (e: React.DragEvent) => {
    if (!hasFiles(e) || disabled) return;
    e.preventDefault();
    dragDepthRef.current += 1;
    setIsDraggingFile(true);
  };

  const handleDragOver = (e: React.DragEvent) => {
    if (!hasFiles(e) || disabled) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!hasFiles(e) || disabled) return;
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDraggingFile(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    if (!hasFiles(e) || disabled) return;
    e.preventDefault();
    dragDepthRef.current = 0;
    setIsDraggingFile(false);
    // Placeholder — attachments aren't wired up yet. Flash a short
    // inline message so the user knows the drop was seen.
    setShowDropFeedback(true);
    window.setTimeout(() => setShowDropFeedback(false), 2500);
  };

  // Auto-resize textarea (max 200px)
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = value.trim();
    if (!content || disabled) return;
    onSend(content);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (mentionOpenRef.current) return;
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
          "flex items-end gap-2 rounded-xl bg-elevated shadow-2 p-2 transition-shadow",
          !isDraggingFile && "focus-within:glow-info",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "Send a message…"}
          className="max-h-[200px] min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 type-body text-fg-primary placeholder:text-fg-disabled focus:outline-none disabled:opacity-40"
          rows={1}
          disabled={disabled}
        />

        {isStreaming ? (
          <button
            type="button"
            onClick={onCancel}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-danger/15 text-danger hover:bg-danger/25 transition-colors"
            aria-label="Stop generation"
          >
            <Square size={16} strokeWidth={2} fill="currentColor" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-info text-canvas hover:opacity-80 transition-opacity disabled:opacity-30 disabled:cursor-not-allowed"
            aria-label="Send message"
          >
            <Send size={16} strokeWidth={2} />
          </button>
        )}
      </div>

      {/* Drop-zone overlay — visual placeholder. File uploads aren't
          wired up yet; dropping a file just flashes the inline notice
          below. `pointer-events-none` keeps the underlying textarea
          focusable while dragging. */}
      {isDraggingFile && (
        <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-info/60 bg-info/10 animate-fade-in-fast">
          <Upload size={18} strokeWidth={1.75} className="text-info" />
          <span className="type-caption-bold text-info">Drop files to attach</span>
          <span className="type-caption text-info/70">Attachments coming soon</span>
        </div>
      )}

      <MentionAutocomplete
        textareaRef={textareaRef}
        value={value}
        onChange={setValue}
        excludeAgentId={agentId}
        onOpenChange={handleMentionOpenChange}
      />

      {showDropFeedback ? (
        <p className="mt-1.5 px-2 type-caption text-warning animate-fade-in-fast">
          File attachments aren&apos;t supported yet — this dropzone is a preview.
        </p>
      ) : (
        <p className="mt-1.5 px-2 type-caption text-fg-disabled flex items-center gap-1.5">
          <Kbd>↵</Kbd>
          <span>to send,</span>
          <Kbd>⇧</Kbd>
          <Kbd>↵</Kbd>
          <span>for new line, type</span>
          <Kbd>@</Kbd>
          <span>to mention an agent.</span>
        </p>
      )}
    </form>
  );
}
