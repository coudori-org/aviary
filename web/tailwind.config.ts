import type { Config } from "tailwindcss";

/**
 * Aviary Slate design system. A small number of legacy Tailwind aliases
 * (brand, info, success, warning, danger, fg.disabled) remain so older
 * call sites continue to compile against status / accent tokens.
 */
const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: [
    "./src/**/*.{ts,tsx,js,jsx}",
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/features/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        hero: ["24px", { lineHeight: "1.2", letterSpacing: "-0.015em", fontWeight: "600" }],
        h1: ["20px", { lineHeight: "1.25", letterSpacing: "-0.012em", fontWeight: "600" }],
        h2: ["16px", { lineHeight: "1.3", letterSpacing: "-0.008em", fontWeight: "600" }],
        h3: ["14px", { lineHeight: "1.35", letterSpacing: "-0.005em", fontWeight: "600" }],
        body: ["13.5px", { lineHeight: "1.55" }],
        small: ["12.5px", { lineHeight: "1.45" }],
        xs: ["11.5px", { lineHeight: "1.4" }],
        over: ["10.5px", { lineHeight: "1.3", letterSpacing: "0.08em", fontWeight: "600" }],
      },
      colors: {
        canvas: "var(--bg-canvas)",
        surface: "var(--bg-surface)",
        raised: "var(--bg-raised)",
        sunk: "var(--bg-sunk)",
        hover: "var(--bg-hover)",
        "bg-active": "var(--bg-active)",
        overlay: "var(--bg-overlay)",

        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent-blue)",
          strong: "var(--accent-blue-strong)",
          soft: "var(--accent-blue-soft)",
          border: "var(--accent-blue-border)",
          bg: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        border: {
          DEFAULT: "var(--border)",
          subtle: "var(--border-subtle)",
          strong: "var(--border-strong)",
        },
        input: "var(--input)",
        ring: "var(--ring)",

        fg: {
          DEFAULT: "var(--fg-primary)",
          primary: "var(--fg-primary)",
          secondary: "var(--fg-secondary)",
          tertiary: "var(--fg-tertiary)",
          muted: "var(--fg-muted)",
          inverse: "var(--fg-inverse)",
          // legacy aliases — disabled maps to muted, on-light to inverse
          disabled: "var(--fg-muted)",
          "on-light": "var(--fg-inverse)",
        },

        status: {
          live: "var(--status-live)",
          "live-soft": "var(--status-live-soft)",
          warn: "var(--status-warn)",
          "warn-soft": "var(--status-warn-soft)",
          error: "var(--status-error)",
          "error-soft": "var(--status-error-soft)",
          info: "var(--status-info)",
          "info-soft": "var(--status-info-soft)",
        },

        // ── legacy aliases — kept so unmigrated call sites still compile. ──
        elevated: "rgb(var(--legacy-elevated) / <alpha-value>)",
        brand: "rgb(var(--legacy-brand) / <alpha-value>)",
        info: "rgb(var(--legacy-info) / <alpha-value>)",
        success: "rgb(var(--legacy-success) / <alpha-value>)",
        warning: "rgb(var(--legacy-warning) / <alpha-value>)",
        danger: "rgb(var(--legacy-danger) / <alpha-value>)",
        "border-base": "rgb(var(--legacy-border-base) / <alpha-value>)",
        "border-strong": "rgb(var(--legacy-border-strong) / <alpha-value>)",
      },
      borderRadius: {
        none: "0",
        micro: "4px",
        xs: "4px",
        sm: "5px",
        DEFAULT: "7px",
        md: "7px",
        lg: "10px",
        xl: "12px",
        "2xl": "16px",
        pill: "9999px",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow-md)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
        // legacy numeric levels
        "1": "var(--shadow-sm)",
        "2": "var(--shadow-md)",
        "3": "var(--shadow-lg)",
        "4": "var(--shadow-xl)",
        "5": "var(--shadow-xl)",
      },
      maxWidth: {
        container: "1200px",
        "container-sm": "960px",
        "container-prose": "768px",
      },
      transitionTimingFunction: {
        panel: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      transitionDuration: {
        fast: "120ms",
        panel: "180ms",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-up": "slide-up 220ms cubic-bezier(0.16, 1, 0.3, 1)",
        pulse: "pulse 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
    require("@tailwindcss/typography"),
  ],
};

export default config;
