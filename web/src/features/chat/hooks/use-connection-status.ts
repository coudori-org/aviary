"use client";

import { useEffect, useRef, useState } from "react";
import type { ConnectionStatus } from "@/lib/ws";

/**
 * useConnectionStatus — debounces intermediate "still connecting" states
 * so fast connections don't flicker their banner UI.
 *
 * Terminal / failure states flip immediately:
 *   - ready, offline, disconnected, reconnecting
 *
 * Intermediate states (connecting / provisioning / spawning / waiting)
 * wait `delayMs` before being surfaced.
 *
 * `reconnecting` is treated as immediate because the user explicitly needs
 * to know recovery is happening — debouncing it would hide the banner
 * during the very window the user is most likely to look at it.
 */
const IMMEDIATE = new Set<ConnectionStatus>([
  "ready",
  "offline",
  "disconnected",
  "reconnecting",
]);

export function useConnectionStatus(raw: ConnectionStatus, delayMs = 500) {
  const [visible, setVisible] = useState<ConnectionStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (IMMEDIATE.has(raw)) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setVisible(raw);
      return;
    }

    if (!timerRef.current) {
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        setVisible(raw);
      }, delayMs);
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [raw, delayMs]);

  return visible;
}
