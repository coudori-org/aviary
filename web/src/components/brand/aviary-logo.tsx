import Image from "next/image";
import logoMark from "@/assets/logo-mark.png";
import { cn } from "@/lib/utils";

interface AviaryLogoProps {
  size?: number;
  className?: string;
}

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
  size?: number;
  className?: string;
  iconOnly?: boolean;
}

export function AviaryLogoMark({ size = 28, className, iconOnly }: AviaryLogoMarkProps) {
  const fontSize = Math.round(size * 0.65);
  return (
    <span className={cn("inline-flex items-center gap-2 leading-none", className)}>
      <AviaryLogo size={size} />
      {!iconOnly && (
        <span
          className="font-semibold tracking-tight text-fg-primary"
          style={{ fontSize, lineHeight: 1 }}
        >
          Aviary
        </span>
      )}
    </span>
  );
}
