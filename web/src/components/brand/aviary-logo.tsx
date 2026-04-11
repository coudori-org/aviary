import Image from "next/image";
import logoMark from "@/assets/logo-mark.png";
import { cn } from "@/lib/utils";

interface AviaryLogoProps {
  /** Visual size in pixels. Defaults to 24. */
  size?: number;
  /** Extra classes applied to the wrapper. */
  className?: string;
}

/**
 * AviaryLogo — brand mark: a perched bird inside a minimalist birdcage,
 * rendered from a transparent PNG asset. Sized by the `size` prop; the
 * aspect ratio of the source image is preserved.
 */
export function AviaryLogo({ size = 24, className }: AviaryLogoProps) {
  return (
    <Image
      src={logoMark}
      alt=""
      width={size}
      height={size}
      priority
      className={cn("block shrink-0 select-none", className)}
      aria-hidden="true"
    />
  );
}

interface AviaryLogoMarkProps {
  /** Visual height of the lockup in pixels (icon ≈ this, text scales). */
  size?: number;
  /** Extra classes applied to the wrapper. */
  className?: string;
  /** Hide the "Aviary" wordmark and show only the icon. */
  iconOnly?: boolean;
}

/**
 * AviaryLogoMark — icon + "Aviary" wordmark lockup. `iconOnly` collapses
 * it to just the icon (used in the collapsed sidebar). The wordmark
 * uses `text-info` so it colour-matches the sky-blue bird mark. The
 * font size scales with `size` so the lockup stays balanced as the
 * icon grows or shrinks.
 */
export function AviaryLogoMark({ size = 28, className, iconOnly }: AviaryLogoMarkProps) {
  const fontSize = Math.round(size * 0.65);
  return (
    <span className={cn("inline-flex items-center gap-2 leading-none", className)}>
      <AviaryLogo size={size} />
      {!iconOnly && (
        <span
          className="font-semibold tracking-tight"
          // Softened variant of the brand sky blue — same hue as the
          // bird mark but with a touch less saturation so the wordmark
          // doesn't glow against the dark sidebar.
          style={{ fontSize, lineHeight: 1, color: "rgb(125, 172, 196)" }}
        >
          Aviary
        </span>
      )}
    </span>
  );
}
