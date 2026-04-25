import { Sparkles } from "@/components/icons";

/**
 * ChatEmptyState — pre-conversation moment.
 */
export function ChatEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 animate-fade-in">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <Sparkles size={24} strokeWidth={1.5} />
      </div>
      <p className="mt-5 type-subheading text-fg-primary">Ready when you are</p>
      <p className="mt-1 type-caption text-fg-muted">Send a message to start the conversation</p>
    </div>
  );
}
