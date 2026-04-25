"use client";

import * as React from "react";

export type Theme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "aviary:theme";

function readInitial(): Theme {
  if (typeof document === "undefined") return "dark";
  const attr = document.documentElement.getAttribute("data-theme");
  return attr === "light" ? "light" : "dark";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>(readInitial);

  const applyTheme = React.useCallback((t: Theme) => {
    document.documentElement.setAttribute("data-theme", t);
    try {
      window.localStorage.setItem(STORAGE_KEY, t);
    } catch {
      // private mode / quota — non-fatal, runtime state is still correct
    }
    setThemeState(t);
  }, []);

  const toggleTheme = React.useCallback(() => {
    applyTheme(theme === "dark" ? "light" : "dark");
  }, [theme, applyTheme]);

  const value = React.useMemo(
    () => ({ theme, setTheme: applyTheme, toggleTheme }),
    [theme, applyTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

/**
 * Inline script — runs before React hydrates so `data-theme` matches the
 * stored preference on the very first paint, no light-flash.
 */
export const THEME_INIT_SCRIPT = `
(function(){
  try {
    var t = window.localStorage.getItem(${JSON.stringify(STORAGE_KEY)});
    if (t === "light" || t === "dark") {
      document.documentElement.setAttribute("data-theme", t);
    }
  } catch (e) {}
})();
`.trim();
