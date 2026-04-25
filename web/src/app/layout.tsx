import type { Metadata } from "next";
import "./globals.css";
import { inter, jetbrainsMono } from "./fonts";
import { AuthProvider } from "@/features/auth/providers/auth-provider";
import { NavigationProgress } from "@/components/feedback/navigation-progress";
import { ThemeProvider, THEME_INIT_SCRIPT } from "@/features/theme/theme-provider";

export const metadata: Metadata = {
  title: "Aviary",
  description: "AI Agent Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" data-accent="blue" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className={`${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}>
        <ThemeProvider>
          <AuthProvider>
            <NavigationProgress />
            {children}
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
