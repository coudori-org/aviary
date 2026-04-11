"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

export type ChatWidth = "comfort" | "wide";

const STORAGE_KEY = "aviary_chat_width";
const DEFAULT_WIDTH: ChatWidth = "comfort";

/**
 * Width preset → max-width Tailwind class.
 *
 * "comfort" matches the legacy `max-w-container-prose` token (768px), so
 * existing chats look unchanged for users who don't touch the toggle.
 */
const WIDTH_CLASS: Record<ChatWidth, string> = {
  comfort: "max-w-[768px]",
  wide: "max-w-[1024px]",
};

interface ChatWidthContextValue {
  width: ChatWidth;
  setWidth: (next: ChatWidth) => void;
  widthClass: string;
}

const ChatWidthContext = createContext<ChatWidthContextValue | null>(null);

/**
 * ChatWidthProvider — owns the user's reading-width preference for the
 * chat surface (header bar, banner, message list, and input).
 *
 * Persisted to localStorage so the choice survives reloads. Initialized
 * from storage in a `useEffect` rather than a lazy initializer to keep
 * SSR happy (no `window` access during the server render).
 */
export function ChatWidthProvider({ children }: { children: React.ReactNode }) {
  const [width, setWidthState] = useState<ChatWidth>(DEFAULT_WIDTH);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "comfort" || stored === "wide") {
      setWidthState(stored);
    }
  }, []);

  const setWidth = useCallback((next: ChatWidth) => {
    setWidthState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
    }
  }, []);

  return (
    <ChatWidthContext.Provider
      value={{ width, setWidth, widthClass: WIDTH_CLASS[width] }}
    >
      {children}
    </ChatWidthContext.Provider>
  );
}

export function useChatWidth(): ChatWidthContextValue {
  const ctx = useContext(ChatWidthContext);
  if (!ctx) throw new Error("useChatWidth must be used within ChatWidthProvider");
  return ctx;
}
