import { MessageSquare } from "@/components/icons";

/**
 * ChatEmptyState — shown when a session has no messages yet and is
 * ready to receive input. Distinct from the EmptyState primitive
 * because it's part of the message stream visually.
 */
export function ChatEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 animate-fade-in">
      <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-elevated shadow-2 text-info">
        <MessageSquare size={22} strokeWidth={1.5} />
      </div>
      <p className="mt-4 type-body text-fg-primary">Ready to chat</p>
      <p className="mt-1 type-caption text-fg-muted">Send a message to start the conversation</p>
    </div>
  );
}
