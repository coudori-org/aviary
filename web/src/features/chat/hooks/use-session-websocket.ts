"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { openSessionSocket } from "@/lib/ws";
import type { ConnectionStatus, WSMessage } from "@/lib/ws";

interface UseSessionWebSocketOptions {
  sessionId: string | undefined;
  enabled: boolean;
  onMessage: (msg: WSMessage) => void;
  /** Called after each successful (re)connection. Used by the chat hook
   *  to reload message history so the UI catches up on anything that
   *  happened during the offline window. */
  onReconnected?: () => void;
}

interface UseSessionWebSocketResult {
  ws: WebSocket | null;
  status: ConnectionStatus;
  statusMessage: string | null;
  /** Seconds remaining until the next automatic reconnect attempt.
   *  Null when not in a backoff window. */
  reconnectIn: number | null;
  /** Trigger an immediate reconnect, bypassing the backoff timer.
   *  No-op if already connecting or already connected. */
  retryNow: () => void;
}

/**
 * useSessionWebSocket — owns the WebSocket lifecycle, including exponential
 * backoff reconnect and a `"reconnecting"` status distinct from initial
 * `"connecting"`. Strict-mode safe via the `connectedRef` guard.
 */

const BACKOFF_DELAYS_MS = [500, 1_000, 2_000, 4_000, 8_000, 16_000, 30_000];

export function useSessionWebSocket({
  sessionId,
  enabled,
  onMessage,
  onReconnected,
}: UseSessionWebSocketOptions): UseSessionWebSocketResult {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [reconnectIn, setReconnectIn] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const connectedRef = useRef(false);
  const cancelledRef = useRef(false);
  const attemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasConnectedOnceRef = useRef(false);

  const onMessageRef = useRef(onMessage);
  const onReconnectedRef = useRef(onReconnected);
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);
  useEffect(() => {
    onReconnectedRef.current = onReconnected;
  }, [onReconnected]);

  const clearReconnectTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (countdownTimerRef.current) {
      clearInterval(countdownTimerRef.current);
      countdownTimerRef.current = null;
    }
    setReconnectIn(null);
  }, []);

  // `retryNow` is exposed via ref so the returned callback stays stable while
  // the underlying connect closure is recreated inside the effect.
  const retryNowRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!sessionId || !enabled) return;
    if (connectedRef.current) return;
    connectedRef.current = true;
    cancelledRef.current = false;
    attemptRef.current = 0;
    hasConnectedOnceRef.current = false;

    const connect = () => {
      if (cancelledRef.current) return;
      clearReconnectTimers();

      const isReconnect = hasConnectedOnceRef.current;
      setStatus(isReconnect ? "reconnecting" : "connecting");
      setStatusMessage(null);

      openSessionSocket(sessionId, {
        onMessage: (msg) => {
          if (cancelledRef.current) return;
          if (msg.type === "status") {
            setStatus(msg.status);
            setStatusMessage(msg.message || null);
            if (msg.status === "ready") {
              attemptRef.current = 0;
              if (isReconnect) {
                // Notify caller so it can refresh history that may have
                // changed during the offline window.
                onReconnectedRef.current?.();
              }
              hasConnectedOnceRef.current = true;
            }
          }
          onMessageRef.current(msg);
        },
        onClose: () => {
          if (cancelledRef.current) return;
          // Forward a synthetic status so consumers can reset streaming state
          onMessageRef.current({ type: "status", status: "disconnected" });
          scheduleReconnect();
        },
        onError: () => {
          // Errors are followed by close — handled there
        },
      })
        .then((ws) => {
          if (cancelledRef.current) {
            ws.close();
            return;
          }
          wsRef.current = ws;
        })
        .catch(() => {
          if (cancelledRef.current) return;
          // Initial open failed (e.g. token refresh failed) — schedule retry
          scheduleReconnect();
        });
    };

    const scheduleReconnect = () => {
      if (cancelledRef.current) return;

      const idx = Math.min(attemptRef.current, BACKOFF_DELAYS_MS.length - 1);
      const delayMs = BACKOFF_DELAYS_MS[idx];
      attemptRef.current += 1;

      setStatus("reconnecting");
      setStatusMessage(null);

      // Countdown ticker for the UI ("Reconnecting in 3s…")
      let remaining = Math.ceil(delayMs / 1_000);
      setReconnectIn(remaining);
      countdownTimerRef.current = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          if (countdownTimerRef.current) clearInterval(countdownTimerRef.current);
          countdownTimerRef.current = null;
          setReconnectIn(null);
        } else {
          setReconnectIn(remaining);
        }
      }, 1_000);

      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, delayMs);
    };

    retryNowRef.current = () => {
      if (cancelledRef.current) return;
      // Bypass the backoff: cancel pending timer and connect immediately
      clearReconnectTimers();
      attemptRef.current = 0;
      connect();
    };

    connect();

    return () => {
      cancelledRef.current = true;
      clearReconnectTimers();
      wsRef.current?.close();
      wsRef.current = null;
      connectedRef.current = false;
    };
  }, [sessionId, enabled, clearReconnectTimers]);

  const retryNow = useCallback(() => retryNowRef.current(), []);

  return { ws: wsRef.current, status, statusMessage, reconnectIn, retryNow };
}
