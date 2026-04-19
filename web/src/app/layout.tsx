import type { Metadata } from "next";
import "./globals.css";
import "highlight.js/styles/github-dark-dimmed.min.css";
import { inter } from "./fonts";
import { AuthProvider } from "@/features/auth/providers/auth-provider";
import { NavigationProgress } from "@/components/feedback/navigation-progress";
import { AuroraBackdrop } from "@/components/brand/aurora-backdrop";

export const metadata: Metadata = {
  title: "Aviary",
  description: "AI Agent Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} font-sans antialiased`}>
        {/* Aurora backdrop sits behind every authenticated + public route.
            Glass surfaces pick up the colour through backdrop-blur. */}
        <AuroraBackdrop />
        <div className="relative z-10">
          <AuthProvider>
            <NavigationProgress />
            {children}
          </AuthProvider>
        </div>
      </body>
    </html>
  );
}
