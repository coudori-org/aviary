import localFont from "next/font/local";

/**
 * Self-hosted variable fonts. Source files in `./fonts/` are extracted from
 * @fontsource-variable/inter and @fontsource-variable/jetbrains-mono (latin
 * subset, weight axis only). No network access at build or runtime.
 */
export const inter = localFont({
  src: [
    { path: "./fonts/inter-variable.woff2", weight: "100 900", style: "normal" },
    { path: "./fonts/inter-variable-italic.woff2", weight: "100 900", style: "italic" },
  ],
  variable: "--font-inter",
  display: "swap",
});

export const jetbrainsMono = localFont({
  src: [
    { path: "./fonts/jetbrains-mono-variable.woff2", weight: "100 800", style: "normal" },
    { path: "./fonts/jetbrains-mono-variable-italic.woff2", weight: "100 800", style: "italic" },
  ],
  variable: "--font-mono",
  display: "swap",
});
