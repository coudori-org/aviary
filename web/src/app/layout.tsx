import type { Metadata } from "next";
import "./globals.css";
import "highlight.js/styles/github-dark-dimmed.min.css";
import { inter } from "./fonts";
import { AuthProvider } from "@/features/auth/providers/auth-provider";

export const metadata: Metadata = {
  title: "Aviary",
  description: "AI Agent Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
