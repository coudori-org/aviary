import { UserBubble } from "./user-bubble";
import { AgentBubble } from "./agent-bubble";
import type { Message } from "@/types";

interface MessageBubbleProps {
  message: Message;
  /** Hide the avatar when this message is part of a same-sender run.
   *  When false, the avatar slot is rendered as an invisible spacer so
   *  content stays horizontally aligned with the run's first message. */
  showAvatar?: boolean;
}

/**
 * MessageBubble — dispatches to the appropriate bubble based on sender_type.
 * The two bubble types intentionally don't share a common shell because
 * their layouts are mirrored (left vs right) and their internal content
 * differs (markdown blocks vs plain text).
 */
export function MessageBubble({ message, showAvatar = true }: MessageBubbleProps) {
  if (message.sender_type === "user") {
    return (
      <UserBubble
        content={message.content}
        showAvatar={showAvatar}
        targetId={`${message.id}/user`}
      />
    );
  }
  return <AgentBubble message={message} showAvatar={showAvatar} />;
}
