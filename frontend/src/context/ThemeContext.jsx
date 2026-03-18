import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ThemeProvider as MuiThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

const ThemeContext = createContext();

// ================================================================
//  AURORA — FINTECH THEME
//  Two palettes: "dark" (deep navy) and "light" (cool white)
//  Edit values here → everything updates everywhere
// ================================================================

// ── Dark Palette ─────────────────────────────────────────────────
const AURORA_DARK = {
    // Backgrounds (layered depth)
    "--bg-primary":    "#060b18",   // deepest — page background
    "--bg-secondary":  "#0d1526",   // cards, panels
    "--bg-tertiary":   "#132038",   // inputs, table rows, dropdowns
    "--bg-hover":      "#1a2d4a",   // hover state rows

    // Borders
    "--border-color":  "#1e3a5f",
    "--border-subtle": "#0f2040",

    // Text
    "--text-primary":  "#e8f0fe",
    "--text-secondary":"#8ba3c7",
    "--text-muted":    "#4a6080",

    // Brand accents
    "--accent-blue":   "#4f9eff",
    "--accent-blue-hover": "#70b3ff",
    "--accent-blue-muted": "rgba(79,158,255,0.12)",

    // Market colours
    "--accent-up":     "#00e676",   // bullish green
    "--accent-down":   "#ff5252",   // bearish red
    "--accent-gold":   "#ffd54f",   // highlight / premium

    // Glow
    "--glow":          "rgba(79,158,255,0.7)",
    "--glow-green":    "rgba(0,230,118,0.5)",
    "--glow-red":      "rgba(255,82,82,0.5)",
};

// ── Light Palette ────────────────────────────────────────────────
const AURORA_LIGHT = {
    // Backgrounds
    "--bg-primary":    "#f0f4ff",   // cool blue-tinted off-white
    "--bg-secondary":  "#ffffff",
    "--bg-tertiary":   "#e4ecf8",
    "--bg-hover":      "#dae6f5",

    // Borders
    "--border-color":  "#c2d3ea",
    "--border-subtle": "#dce8f5",

    // Text
    "--text-primary":  "#0a1929",
    "--text-secondary":"#3d5a7a",
    "--text-muted":    "#7a9bbf",

    // Brand accents
    "--accent-blue":   "#1565c0",
    "--accent-blue-hover": "#0d47a1",
    "--accent-blue-muted": "rgba(21,101,192,0.1)",

    // Market colours
    "--accent-up":     "#1b5e20",
    "--accent-down":   "#b71c1c",
    "--accent-gold":   "#e65100",

    // Glow
    "--glow":          "rgba(21,101,192,0.4)",
    "--glow-green":    "rgba(27,94,32,0.3)",
    "--glow-red":      "rgba(183,28,28,0.3)",
};

// ================================================================
//  LAYOUT TOKENS — control spacing & structure from here
// ================================================================
export const LAYOUT = {
    navbarHeight:    "60px",
    sidebarWidth:    "240px",
    sidebarCollapsed:"64px",
    cardRadius:      "12px",
    inputRadius:     "8px",
    buttonRadius:    "8px",
    chipRadius:      "6px",
    contentPadding:  "1.5rem",
    maxWidth:        "1400px",
};

// ================================================================
//  TYPOGRAPHY TOKENS
// ================================================================
export const TYPOGRAPHY = {
    fontBody:    "'DM Sans', 'Segoe UI', sans-serif",
    fontDisplay: "'Syne', sans-serif",        // headings, hero text
    fontMono:    "'JetBrains Mono', 'Fira Code', monospace", // prices, tickers
    baseSize:    "14px",                      // 1rem = 14px
    weightNormal: 400,
    weightMedium: 500,
    weightSemiBold: 600,
    weightBold: 700,
};

// ================================================================
//  SHADOW TOKENS
// ================================================================
export const SHADOWS = {
    card:        "0 1px 4px rgba(0,0,0,0.2)",
    cardHover:   "0 6px 20px rgba(0,0,0,0.35)",
    glowBlue:    "0 0 18px rgba(79,158,255,0.3)",
    glowGreen:   "0 0 14px rgba(0,230,118,0.3)",
    glowRed:     "0 0 14px rgba(255,82,82,0.3)",
    input:       "inset 0 1px 3px rgba(0,0,0,0.15)",
};

// ================================================================
//  MUI THEME FACTORY
//  Builds a full MUI theme from the active palette
// ================================================================
function buildMuiTheme(mode) {
    const p = mode === "dark" ? AURORA_DARK : AURORA_LIGHT;

    return createTheme({
        palette: {
            mode,
            background: {
                default: p["--bg-primary"],
                paper:   p["--bg-secondary"],
            },
            text: {
                primary:   p["--text-primary"],
                secondary: p["--text-secondary"],
                disabled:  p["--text-muted"],
            },
            primary: {
                main:  p["--accent-blue"],
                light: p["--accent-blue-hover"],
                dark:  p["--accent-blue-hover"],
            },
            success: { main: p["--accent-up"]   },
            error:   { main: p["--accent-down"] },
            warning: { main: p["--accent-gold"] },
            divider: p["--border-color"],
        },

        typography: {
            fontFamily:  TYPOGRAPHY.fontBody,
            fontSize:    13,
            h1: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: TYPOGRAPHY.weightBold,    letterSpacing: "-0.02em" },
            h2: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: TYPOGRAPHY.weightBold,    letterSpacing: "-0.02em" },
            h3: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: TYPOGRAPHY.weightSemiBold, letterSpacing: "-0.01em" },
            h4: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: TYPOGRAPHY.weightSemiBold },
            h5: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: TYPOGRAPHY.weightMedium  },
            h6: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: TYPOGRAPHY.weightMedium  },
            body1: { fontFamily: TYPOGRAPHY.fontBody, fontSize: "0.875rem" },
            body2: { fontFamily: TYPOGRAPHY.fontBody, fontSize: "0.8rem", color: p["--text-secondary"] },
            caption: { fontFamily: TYPOGRAPHY.fontMono, fontSize: "0.75rem" },
        },

        shape: { borderRadius: 12 },

        components: {
            // ── Card ──────────────────────────────────────
            MuiCard: {
                styleOverrides: {
                    root: {
                        background:   p["--bg-secondary"],
                        border:       `1px solid ${p["--border-color"]}`,
                        borderRadius: LAYOUT.cardRadius,
                        boxShadow:    SHADOWS.card,
                        transition:   "transform 0.2s ease, box-shadow 0.2s ease",
                        "&:hover": {
                            transform:  "translateY(-2px)",
                            boxShadow:  SHADOWS.cardHover,
                        },
                    },
                },
            },

            // ── Text Field ────────────────────────────────
            MuiTextField: {
                styleOverrides: {
                    root: {
                        "& .MuiOutlinedInput-root": {
                            color:        p["--text-primary"],
                            background:   p["--bg-tertiary"],
                            borderRadius: LAYOUT.inputRadius,
                            fontSize:     "0.875rem",
                            "& fieldset":             { borderColor: p["--border-color"] },
                            "&:hover fieldset":       { borderColor: p["--accent-blue"]  },
                            "&.Mui-focused fieldset": { borderColor: p["--accent-blue"], borderWidth: "1.5px" },
                        },
                        "& .MuiInputLabel-root": {
                            color: p["--text-secondary"],
                            fontSize: "0.875rem",
                            "&.Mui-focused": { color: p["--accent-blue"] },
                        },
                    },
                },
            },

            // ── Button ────────────────────────────────────
            MuiButton: {
                styleOverrides: {
                    root: {
                        borderRadius:  LAYOUT.buttonRadius,
                        textTransform: "none",
                        fontWeight:    TYPOGRAPHY.weightSemiBold,
                        fontSize:      "0.875rem",
                        letterSpacing: "0.01em",
                        transition:    "all 0.15s ease",
                    },
                    containedPrimary: {
                        background: p["--accent-blue"],
                        boxShadow:  SHADOWS.glowBlue,
                        "&:hover": {
                            background: p["--accent-blue-hover"],
                            boxShadow:  `0 0 24px ${p["--glow"]}`,
                        },
                    },
                    outlinedPrimary: {
                        borderColor: p["--border-color"],
                        color:       p["--text-primary"],
                        "&:hover": {
                            borderColor:     p["--accent-blue"],
                            backgroundColor: p["--accent-blue-muted"],
                        },
                    },
                },
            },

            // ── Tabs ──────────────────────────────────────
            MuiTabs: {
                styleOverrides: {
                    root:      { minHeight: 40 },
                    indicator: { backgroundColor: p["--accent-blue"], height: "2px" },
                },
            },
            MuiTab: {
                styleOverrides: {
                    root: {
                        color:        p["--text-secondary"],
                        textTransform:"none",
                        fontWeight:   TYPOGRAPHY.weightMedium,
                        minHeight:    40,
                        fontSize:     "0.875rem",
                        "&.Mui-selected": { color: p["--accent-blue"] },
                    },
                },
            },

            // ── Divider ───────────────────────────────────
            MuiDivider: {
                styleOverrides: {
                    root: { borderColor: p["--border-color"] },
                },
            },

            // ── Dialog ────────────────────────────────────
            MuiDialog: {
                styleOverrides: {
                    paper: {
                        background:   p["--bg-secondary"],
                        border:       `1px solid ${p["--border-color"]}`,
                        borderRadius: LAYOUT.cardRadius,
                        boxShadow:    SHADOWS.cardHover,
                    },
                },
            },

            // ── Table ─────────────────────────────────────
            MuiTableHead: {
                styleOverrides: {
                    root: { background: p["--bg-tertiary"] },
                },
            },
            MuiTableCell: {
                styleOverrides: {
                    root: {
                        borderColor: p["--border-color"],
                        color:       p["--text-primary"],
                        fontSize:    "0.8rem",
                        padding:     "10px 14px",
                    },
                    head: {
                        color:      p["--text-secondary"],
                        fontWeight: TYPOGRAPHY.weightSemiBold,
                        fontFamily: TYPOGRAPHY.fontBody,
                        fontSize:   "0.75rem",
                        letterSpacing: "0.05em",
                        textTransform: "uppercase",
                    },
                },
            },
            MuiTableRow: {
                styleOverrides: {
                    root: {
                        transition: "background 0.15s ease",
                        "&:hover": { background: p["--bg-hover"] },
                    },
                },
            },

            // ── Chip ──────────────────────────────────────
            MuiChip: {
                styleOverrides: {
                    root: {
                        borderRadius: LAYOUT.chipRadius,
                        fontSize:     "0.75rem",
                        fontWeight:   TYPOGRAPHY.weightMedium,
                        height:       "24px",
                    },
                },
            },

            // ── Tooltip ───────────────────────────────────
            MuiTooltip: {
                styleOverrides: {
                    tooltip: {
                        background:   p["--bg-tertiary"],
                        border:       `1px solid ${p["--border-color"]}`,
                        color:        p["--text-primary"],
                        fontSize:     "0.75rem",
                        borderRadius: LAYOUT.chipRadius,
                    },
                    arrow: { color: p["--bg-tertiary"] },
                },
            },

            // ── Select / Menu ─────────────────────────────
            MuiMenu: {
                styleOverrides: {
                    paper: {
                        background:   p["--bg-secondary"],
                        border:       `1px solid ${p["--border-color"]}`,
                        borderRadius: LAYOUT.inputRadius,
                        boxShadow:    SHADOWS.cardHover,
                    },
                },
            },
            MuiMenuItem: {
                styleOverrides: {
                    root: {
                        fontSize:   "0.875rem",
                        color:      p["--text-primary"],
                        "&:hover":  { background: p["--bg-hover"] },
                        "&.Mui-selected": {
                            background: p["--accent-blue-muted"],
                            color:      p["--accent-blue"],
                        },
                    },
                },
            },
        },
    });
}

// ================================================================
//  CSS VARIABLE INJECTOR
//  Injects palette + layout + typography into :root
// ================================================================
function injectCSSVariables(mode) {
    const root    = document.documentElement;
    const palette = mode === "dark" ? AURORA_DARK : AURORA_LIGHT;

    // Inject colour palette
    Object.entries(palette).forEach(([key, value]) => {
        root.style.setProperty(key, value);
    });

    // Inject layout tokens
    root.style.setProperty("--navbar-height",     LAYOUT.navbarHeight);
    root.style.setProperty("--sidebar-width",     LAYOUT.sidebarWidth);
    root.style.setProperty("--sidebar-collapsed", LAYOUT.sidebarCollapsed);
    root.style.setProperty("--card-radius",       LAYOUT.cardRadius);
    root.style.setProperty("--input-radius",      LAYOUT.inputRadius);
    root.style.setProperty("--button-radius",     LAYOUT.buttonRadius);
    root.style.setProperty("--content-padding",   LAYOUT.contentPadding);
    root.style.setProperty("--max-width",         LAYOUT.maxWidth);

    // Inject typography tokens
    root.style.setProperty("--font-body",    TYPOGRAPHY.fontBody);
    root.style.setProperty("--font-display", TYPOGRAPHY.fontDisplay);
    root.style.setProperty("--font-mono",    TYPOGRAPHY.fontMono);

    // Inject shadows
    root.style.setProperty("--shadow-card",      SHADOWS.card);
    root.style.setProperty("--shadow-card-hover",SHADOWS.cardHover);
    root.style.setProperty("--shadow-glow-blue", SHADOWS.glowBlue);
    root.style.setProperty("--shadow-glow-green",SHADOWS.glowGreen);
    root.style.setProperty("--shadow-glow-red",  SHADOWS.glowRed);
}

// ================================================================
//  PROVIDER
// ================================================================
export const ThemeProvider = ({ children }) => {
    const [theme, setTheme] = useState(() => {
        // Priority: 1. saved  2. system preference  3. dark
        const saved  = localStorage.getItem("theme");
        const active = (saved === "light" || saved === "dark")
            ? saved
            : window.matchMedia("(prefers-color-scheme: light)").matches
                ? "light"
                : "dark";

        // ── CRITICAL: inject BEFORE first render ──────────────────
        // useEffect fires AFTER render — one frame with no vars = flash.
        // Injecting here means vars exist before any component paints.
        injectCSSVariables(active);
        document.documentElement.classList.toggle("dark",  active === "dark");
        document.documentElement.classList.toggle("light", active === "light");
        document.documentElement.style.fontSize = TYPOGRAPHY.baseSize;
        localStorage.setItem("theme", active);

        return active;
    });

    // Runs on every subsequent toggle after mount
    useEffect(() => {
        injectCSSVariables(theme);
        document.documentElement.classList.toggle("dark",  theme === "dark");
        document.documentElement.classList.toggle("light", theme === "light");
        document.documentElement.style.fontSize = TYPOGRAPHY.baseSize;
        localStorage.setItem("theme", theme);
    }, [theme]);

    const toggleTheme = () =>
        setTheme((prev) => (prev === "dark" ? "light" : "dark"));

    const muiTheme = useMemo(() => buildMuiTheme(theme), [theme]);

    return (
        <ThemeContext.Provider value={{ theme, toggleTheme }}>
            <MuiThemeProvider theme={muiTheme}>
                <CssBaseline />
                {children}
            </MuiThemeProvider>
        </ThemeContext.Provider>
    );
};

// ================================================================
//  HOOK
// ================================================================
export const useTheme = () => useContext(ThemeContext);
