"use client";

import { useState, useEffect, useRef } from "react";
import { Play, X } from "@/components/icons";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface RunDialogProps {
  open: boolean;
  onClose: () => void;
  onRun: (triggerData: Record<string, unknown>) => void;
}

export function RunDialog({ open, onClose, onRun }: RunDialogProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setInput("");
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [open]);

  const handleSubmit = () => {
    onRun({ text: input });
    onClose();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Dialog */}
      <div className="relative w-full max-w-md rounded-lg border border-white/[0.06] bg-[rgb(16_17_17)] shadow-5">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
          <h3 className="text-[13px] font-medium text-fg-primary">Run Workflow</h3>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-fg-disabled hover:text-fg-muted transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        <div className="px-4 py-4 space-y-3">
          <div className="space-y-1.5">
            <label className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
              Trigger Input
            </label>
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={4}
              placeholder="Enter input text for the workflow…"
              className="text-[13px]"
            />
            <p className="text-[10px] text-fg-disabled">
              This text is passed as the Manual Trigger output. Ctrl+Enter to run.
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t border-white/[0.06]">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-3 py-1.5 text-[12px] font-medium text-fg-muted hover:text-fg-primary hover:bg-white/[0.04] transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-medium bg-success/10 text-success hover:bg-success/20 transition-colors"
          >
            <Play size={12} strokeWidth={2.5} />
            Run
          </button>
        </div>
      </div>
    </div>
  );
}
