"use client";

import { createContext, useContext } from "react";

interface ChatSearchContextValue {
  query: string;
  currentTargetId: string | null;
}

const ChatSearchContext = createContext<ChatSearchContextValue>({
  query: "",
  currentTargetId: null,
});

/**
 * Broadcasts the live search query and active target id down the chat
 * tree so individual blocks can auto-expand and paint highlight rings
 * without prop drilling.
 */
export function ChatSearchContextProvider({
  query,
  currentTargetId,
  children,
}: {
  query: string;
  currentTargetId: string | null;
  children: React.ReactNode;
}) {
  return (
    <ChatSearchContext.Provider value={{ query, currentTargetId }}>
      {children}
    </ChatSearchContext.Provider>
  );
}

export function useChatSearchQuery(): string {
  return useContext(ChatSearchContext).query;
}

export function useChatSearchTargetId(): string | null {
  return useContext(ChatSearchContext).currentTargetId;
}
