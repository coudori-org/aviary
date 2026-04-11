"use client";

import { useEffect } from "react";

interface HotkeyOptions {
  /** Modifier requirements: "mod" matches Cmd on macOS / Ctrl elsewhere. */
  mod?: boolean;
  shift?: boolean;
  alt?: boolean;
  /** Skip the handler when focus is in an input/textarea. Default: true. */
  ignoreInputs?: boolean;
}

const isMac =
  typeof navigator !== "undefined" && /(Mac|iPhone|iPad)/.test(navigator.platform);

function isEditableTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return el.isContentEditable;
}

/**
 * useHotkey — bind a global keyboard shortcut.
 *
 * Usage:
 *   useHotkey("k", () => openPalette(), { mod: true });
 */
export function useHotkey(
  key: string,
  handler: (e: KeyboardEvent) => void,
  options: HotkeyOptions = {},
) {
  const { mod = false, shift = false, alt = false, ignoreInputs = true } = options;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== key.toLowerCase()) return;

      const wantsMod = mod && (isMac ? e.metaKey : e.ctrlKey);
      if (mod !== wantsMod) return;
      if (shift !== e.shiftKey) return;
      if (alt !== e.altKey) return;
      if (ignoreInputs && isEditableTarget(e.target)) return;

      handler(e);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [key, handler, mod, shift, alt, ignoreInputs]);
}
