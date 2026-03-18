/** @type {import('tailwindcss').Config} */
// ================================================================
//  tailwind.config.js — AURORA FINTECH THEME
//  All values point to CSS variables injected by ThemeContext.jsx
//  DO NOT hardcode hex here. Edit colours in ThemeContext.jsx only.
// ================================================================

export default {
    darkMode: "class", // toggled via html.dark by ThemeContext
    content:  ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],

    theme: {
        extend: {

            // ── Colours ─────────────────────────────────────────
            // CSS vars stay in sync with ThemeContext automatically
            colors: {
                "bg-primary":     "var(--bg-primary)",
                "bg-secondary":   "var(--bg-secondary)",
                "bg-tertiary":    "var(--bg-tertiary)",
                "bg-hover":       "var(--bg-hover)",

                "text-primary":   "var(--text-primary)",
                "text-secondary": "var(--text-secondary)",
                "text-muted":     "var(--text-muted)",

                "accent-blue":    "var(--accent-blue)",
                "accent-green":   "var(--accent-up)",
                "accent-red":     "var(--accent-down)",
                "accent-gold":    "var(--accent-gold)",

                "border-base":    "var(--border-color)",
                "border-subtle":  "var(--border-subtle)",
            },

            // ── Typography ──────────────────────────────────────
            fontFamily: {
                sans:    ["DM Sans",        "Segoe UI", "sans-serif"],
                display: ["Syne",           "sans-serif"],
                mono:    ["JetBrains Mono", "Fira Code", "monospace"],
            },

            // ── Border Radius ───────────────────────────────────
            borderRadius: {
                card:  "12px",
                input: "8px",
                chip:  "6px",
            },

            // ── Shadows ─────────────────────────────────────────
            boxShadow: {
                card:         "var(--shadow-card)",
                "card-hover": "var(--shadow-card-hover)",
                "glow-blue":  "var(--shadow-glow-blue)",
                "glow-green": "var(--shadow-glow-green)",
                "glow-red":   "var(--shadow-glow-red)",
            },

            // ── Layout Sizing ────────────────────────────────────
            height:   { navbar:             "var(--navbar-height)"    },
            width:    { sidebar:            "var(--sidebar-width)",
                        "sidebar-collapsed":"var(--sidebar-collapsed)" },
            maxWidth: { content:            "var(--max-width)"        },
            padding:  { content:            "var(--content-padding)"  },

            // ── Transitions ──────────────────────────────────────
            transitionDuration: {
                fast: "150ms",
                base: "250ms",
                slow: "500ms",
            },
            transitionTimingFunction: {
                spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
            },
        },
    },

    plugins: [],
};
