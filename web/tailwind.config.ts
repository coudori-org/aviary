import type { Config } from "tailwindcss";

/**
 * Tailwind config — wired to the design tokens defined in src/styles/tokens.css.
 *
 * Color tokens are exposed both as semantic names (canvas, fg, brand) and via
 * the `rgb(var(--token) / <alpha>)` pattern so utilities like `bg-canvas/50`
 * work for translucency.
 */
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "Inter Fallback", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // Surfaces
        canvas: "rgb(var(--bg-canvas) / <alpha-value>)",
        elevated: "rgb(var(--bg-elevated) / <alpha-value>)",
        raised: "rgb(var(--bg-raised) / <alpha-value>)",

        // Foreground (text)
        fg: {
          DEFAULT: "rgb(var(--fg-primary) / <alpha-value>)",
          primary: "rgb(var(--fg-primary) / <alpha-value>)",
          secondary: "rgb(var(--fg-secondary) / <alpha-value>)",
          tertiary: "rgb(var(--fg-tertiary) / <alpha-value>)",
          muted: "rgb(var(--fg-muted) / <alpha-value>)",
          disabled: "rgb(var(--fg-disabled) / <alpha-value>)",
          "on-light": "rgb(var(--fg-on-light) / <alpha-value>)",
        },

        // Brand & intents
        brand: "rgb(var(--brand-accent) / <alpha-value>)",
        info: "rgb(var(--intent-info) / <alpha-value>)",
        success: "rgb(var(--intent-success) / <alpha-value>)",
        warning: "rgb(var(--intent-warning) / <alpha-value>)",
        danger: "rgb(var(--intent-danger) / <alpha-value>)",

        // Borders
        "border-base": "rgb(var(--border-base) / <alpha-value>)",
        "border-strong": "rgb(var(--border-strong) / <alpha-value>)",
      },
      borderRadius: {
        none: "0",
        micro: "var(--radius-micro)",
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        DEFAULT: "var(--radius-md)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
        pill: "var(--radius-pill)",
      },
      boxShadow: {
        none: "var(--shadow-0)",
        "1": "var(--shadow-1)",
        "2": "var(--shadow-2)",
        "3": "var(--shadow-3)",
        "4": "var(--shadow-4)",
        "5": "var(--shadow-5)",
      },
      maxWidth: {
        "container": "1200px",
        "container-sm": "960px",
        "container-prose": "768px",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
