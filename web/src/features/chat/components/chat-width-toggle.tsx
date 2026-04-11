"use client";

import { RectangleVertical, RectangleHorizontal } from "@/components/icons";
import { useChatWidth, type ChatWidth } from "@/features/chat/hooks/use-chat-width";
import { cn } from "@/lib/utils";

const OPTIONS: {
  value: ChatWidth;
  label: string;
  Icon: typeof RectangleVertical;
}[] = [
  { value: "comfort", label: "Comfortable width", Icon: RectangleVertical },
  { value: "wide", label: "Wide width", Icon: RectangleHorizontal },
];

/**
 * ChatWidthToggle — segmented control in the chat header for switching
 * the reading width between comfort and wide presets.
 *
 * Sized to match the neighboring header action buttons (h-7 w-7) so the
 * click target is comfortable while the visual stays compact.
 */
export function ChatWidthToggle() {
  const { width, setWidth } = useChatWidth();

  return (
    <div
      role="tablist"
      aria-label="Chat width"
      className="flex items-center gap-0 rounded-xs border border-white/[0.06] bg-canvas p-0.5"
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = width === value;
        return (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={label}
            title={label}
            onClick={() => setWidth(value)}
            className={cn(
              "flex h-6 w-7 items-center justify-center rounded-xs transition-colors",
              active
                ? "bg-raised text-fg-primary"
                : "text-fg-muted hover:text-fg-primary",
            )}
          >
            <Icon size={14} strokeWidth={1.75} />
          </button>
        );
      })}
    </div>
  );
}
