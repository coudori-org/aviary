import { Inter } from "next/font/google";

/**
 * Inter — primary sans-serif. Loaded via next/font for self-hosting + CLS prevention.
 *
 * GeistMono is referenced in CSS via --font-geist-mono but falls back to system mono
 * since it's not yet packaged here. Adding a local woff2 file would be the next
 * upgrade, but the system mono looks identical at the sizes we use.
 */
export const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});
