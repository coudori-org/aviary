"use client";

import * as React from "react";

export interface ChatActions {
  /** Current persisted title; `null` when the session has none. */
  sessionTitle: string | null;
  /** Persist a new title. Outer layout owns the input/draft state; this
   *  callback only mirrors the optimistic update + REST PATCH. */
  saveTitle: (next: string) => Promise<void>;
  hasMessages: boolean;
  onPrintVisual: () => void;
  onExportText: () => void;
}

/** Read-only channel — consumers (e.g. AgentSubHeader) re-render when
 *  actions change. Kept separate from the setter so publishing never
 *  re-runs the publisher. */
const ValueContext = React.createContext<ChatActions | null>(null);

/** Setter channel — the dispatch from useState is referentially stable,
 *  so subscribers (publishers) don't re-render on every actions update. */
const SetterContext = React.createContext<
  React.Dispatch<React.SetStateAction<ChatActions | null>> | null
>(null);

/**
 * Surfaces ChatView's per-session actions (inline title edit + print/export
 * + message presence) so an outer layout — e.g. AgentSubHeader on the
 * agent chat page — can render them while ChatView itself runs with
 * `hideHeader`. Two-context split avoids the infinite-update loop that
 * happens if the publisher subscribes to the value it's publishing.
 */
export function ChatActionsProvider({ children }: { children: React.ReactNode }) {
  const [actions, setActions] = React.useState<ChatActions | null>(null);
  return (
    <SetterContext.Provider value={setActions}>
      <ValueContext.Provider value={actions}>{children}</ValueContext.Provider>
    </SetterContext.Provider>
  );
}

/** Read the actions; returns null when no ChatView is mounted (or no
 *  provider is wrapping). */
export function useChatActions(): ChatActions | null {
  return React.useContext(ValueContext);
}

/** Internal — used by ChatView to publish/clear its actions. Falls back
 *  to a no-op when no provider is mounted (chat usable standalone). */
export function usePublishChatActions(actions: ChatActions | null): void {
  const setActions = React.useContext(SetterContext);
  React.useEffect(() => {
    if (!setActions) return;
    setActions(actions);
    return () => setActions(null);
  }, [setActions, actions]);
}
