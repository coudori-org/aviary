"use client";

import { useEffect, useRef } from "react";

interface RenameInputProps {
  initialValue: string;
  placeholder?: string;
  depth: number;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}

/** Inline input rendered inside the file tree for New/Rename flows. */
export function RenameInput({
  initialValue,
  placeholder,
  depth,
  onSubmit,
  onCancel,
}: RenameInputProps) {
  const ref = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    const dotIdx = initialValue.lastIndexOf(".");
    if (dotIdx > 0) {
      el.setSelectionRange(0, dotIdx);
    } else {
      el.select();
    }
  }, [initialValue]);

  return (
    <div
      className="flex items-center gap-1 py-0.5"
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
    >
      <input
        ref={ref}
        defaultValue={initialValue}
        placeholder={placeholder}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            onCancel();
            return;
          }
          if (e.nativeEvent.isComposing || e.keyCode === 229) return;
          if (e.key === "Enter") {
            const v = (e.currentTarget.value ?? "").trim();
            if (v) onSubmit(v);
            else onCancel();
          }
        }}
        onBlur={(e) => {
          const v = (e.currentTarget.value ?? "").trim();
          if (!v || v === initialValue) {
            onCancel();
          } else {
            onSubmit(v);
          }
        }}
        className="flex-1 rounded-xs border border-info/40 bg-canvas px-1.5 py-0.5 type-caption text-fg-primary outline-none focus:border-info"
      />
    </div>
  );
}
