interface TimeDividerProps {
  label: string;
}

/**
 * TimeDivider — centered text label flanked by hairlines, used to break
 * up long sessions visually when there's a meaningful gap between
 * consecutive messages or when the conversation crosses calendar days.
 *
 * Pure presentation — `MessageList` decides when to render one and what
 * the label should say (via `computeTimeDividerLabel`).
 */
export function TimeDivider({ label }: TimeDividerProps) {
  return (
    <div className="my-3 flex items-center gap-3" role="separator" aria-label={label}>
      <div className="h-px flex-1 bg-white/[0.06]" />
      <span className="type-caption text-fg-disabled tabular-nums">{label}</span>
      <div className="h-px flex-1 bg-white/[0.06]" />
    </div>
  );
}
