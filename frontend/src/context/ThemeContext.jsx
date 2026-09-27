import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ThemeProvider as MuiThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

const ThemeContext = createContext(null);

// Institutional surface presets: restrained contrast, opaque work surfaces and
// low-saturation semantic colours suitable for long market-monitoring sessions.
export const THEME_PRESETS = {
    midnight: {
        label: "Institutional Navy",
        description: "Deep navy execution workspace",
        preview: ["#08111d", "#111d2d", "#3c78a8"],
        dark: {
            "--bg-primary": "#08111d", "--bg-secondary": "#0d1724", "--bg-elevated": "#111d2d",
            "--bg-tertiary": "#152234", "--bg-hover": "#19283c", "--border-color": "#26364b",
            "--border-subtle": "#1b2a3d", "--text-primary": "#e6edf5", "--text-secondary": "#9aa9ba",
            "--text-muted": "#65758a", "--accent-up": "#3a9b72", "--accent-down": "#c65d63",
            "--accent-gold": "#ad8b47", "--surface-glass": "#0d1724",
            "--surface-glass-strong": "#0b1521", "--glow-green": "rgba(58,155,114,0.12)",
            "--glow-red": "rgba(198,93,99,0.12)", "--page-gradient": "#08111d",
        },
        light: {
            "--bg-primary": "#f1f4f7", "--bg-secondary": "#ffffff", "--bg-elevated": "#f8fafc",
            "--bg-tertiary": "#e8edf3", "--bg-hover": "#e1e7ee", "--border-color": "#cbd4df",
            "--border-subtle": "#dde3ea", "--text-primary": "#172334", "--text-secondary": "#566579",
            "--text-muted": "#7b899a", "--accent-up": "#247753", "--accent-down": "#aa4d54",
            "--accent-gold": "#876c35", "--surface-glass": "#ffffff",
            "--surface-glass-strong": "#f8fafc", "--glow-green": "rgba(36,119,83,0.10)",
            "--glow-red": "rgba(170,77,84,0.10)", "--page-gradient": "#f1f4f7",
        },
    },
    graphite: {
        label: "Execution Slate",
        description: "Neutral low-glare trading surface",
        preview: ["#0c1117", "#19212b", "#607d9a"],
        dark: {
            "--bg-primary": "#0c1117", "--bg-secondary": "#121820", "--bg-elevated": "#161d26",
            "--bg-tertiary": "#19212b", "--bg-hover": "#202a35", "--border-color": "#2b3744",
            "--border-subtle": "#202a34", "--text-primary": "#e7ebef", "--text-secondary": "#a1abb6",
            "--text-muted": "#6e7a87", "--accent-up": "#4a9572", "--accent-down": "#bd6267",
            "--accent-gold": "#a58a55", "--surface-glass": "#121820",
            "--surface-glass-strong": "#10161d", "--glow-green": "rgba(74,149,114,0.10)",
            "--glow-red": "rgba(189,98,103,0.10)", "--page-gradient": "#0c1117",
        },
        light: {
            "--bg-primary": "#f3f4f5", "--bg-secondary": "#ffffff", "--bg-elevated": "#fafbfc",
            "--bg-tertiary": "#e9ecef", "--bg-hover": "#e2e6ea", "--border-color": "#cdd3da",
            "--border-subtle": "#dfe3e7", "--text-primary": "#202832", "--text-secondary": "#58636f",
            "--text-muted": "#818b96", "--accent-up": "#307554", "--accent-down": "#a94e53",
            "--accent-gold": "#806b40", "--surface-glass": "#ffffff",
            "--surface-glass-strong": "#fafbfc", "--glow-green": "rgba(48,117,84,0.08)",
            "--glow-red": "rgba(169,78,83,0.08)", "--page-gradient": "#f3f4f5",
        },
    },
    ocean: {
        label: "Research Teal",
        description: "Measured teal for research workflows",
        preview: ["#081516", "#142727", "#2e7d72"],
        dark: {
            "--bg-primary": "#081516", "--bg-secondary": "#0d1c1d", "--bg-elevated": "#112324",
            "--bg-tertiary": "#142727", "--bg-hover": "#1a3131", "--border-color": "#294140",
            "--border-subtle": "#1c3333", "--text-primary": "#e4eeec", "--text-secondary": "#96aaa6",
            "--text-muted": "#667d79", "--accent-up": "#3b9470", "--accent-down": "#bd6269",
            "--accent-gold": "#a78a50", "--surface-glass": "#0d1c1d",
            "--surface-glass-strong": "#0b191a", "--glow-green": "rgba(59,148,112,0.10)",
            "--glow-red": "rgba(189,98,105,0.10)", "--page-gradient": "#081516",
        },
        light: {
            "--bg-primary": "#f0f5f4", "--bg-secondary": "#ffffff", "--bg-elevated": "#f8fbfa",
            "--bg-tertiary": "#e5ecea", "--bg-hover": "#dce6e3", "--border-color": "#c5d3d0",
            "--border-subtle": "#d8e2e0", "--text-primary": "#1b2d2c", "--text-secondary": "#566d69",
            "--text-muted": "#7b918d", "--accent-up": "#2b7657", "--accent-down": "#a95057",
            "--accent-gold": "#816d42", "--surface-glass": "#ffffff",
            "--surface-glass-strong": "#f8fbfa", "--glow-green": "rgba(43,118,87,0.08)",
            "--glow-red": "rgba(169,80,87,0.08)", "--page-gradient": "#f0f5f4",
        },
    },
};

export const ACCENT_PRESETS = {
    cyan: { hex: "#3C78A8", muted: "rgba(60,120,168,0.14)", hover: "#4B87B7", glow: "rgba(60,120,168,0.12)", contrast: "#ffffff" },
    emerald: { hex: "#2E7D72", muted: "rgba(46,125,114,0.14)", hover: "#398B80", glow: "rgba(46,125,114,0.12)", contrast: "#ffffff" },
    purple: { hex: "#5B6F8E", muted: "rgba(91,111,142,0.14)", hover: "#6A7E9D", glow: "rgba(91,111,142,0.12)", contrast: "#ffffff" },
    amber: { hex: "#927640", muted: "rgba(146,118,64,0.14)", hover: "#A0844E", glow: "rgba(146,118,64,0.10)", contrast: "#ffffff" },
    rose: { hex: "#9B5360", muted: "rgba(155,83,96,0.14)", hover: "#AA626E", glow: "rgba(155,83,96,0.10)", contrast: "#ffffff" },
};

export const LAYOUT = {
    navbarHeight: "56px", sidebarWidth: "232px", sidebarCollapsed: "64px",
    cardRadius: "6px", inputRadius: "4px", buttonRadius: "4px", chipRadius: "3px",
    contentPadding: "1.25rem", maxWidth: "1600px",
};

export const TYPOGRAPHY = {
    fontBody: "'Inter', 'Segoe UI', sans-serif",
    fontDisplay: "'Inter', 'Segoe UI', sans-serif",
    fontMono: "'IBM Plex Mono', 'Cascadia Mono', Consolas, monospace",
    baseSize: "13px", weightNormal: 400, weightMedium: 500, weightSemiBold: 600, weightBold: 700,
};

function getPalette(mode, presetKey) {
    const preset = THEME_PRESETS[presetKey] || THEME_PRESETS.midnight;
    return preset[mode === "dark" ? "dark" : "light"];
}

function getSystemTheme() {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function buildMuiTheme(mode, presetKey, accentKey) {
    const p = getPalette(mode, presetKey);
    const accent = ACCENT_PRESETS[accentKey] || ACCENT_PRESETS.cyan;
    const cardShadow = mode === "dark" ? "0 1px 2px rgba(0,0,0,0.28)" : "0 1px 2px rgba(15,23,42,0.06)";

    return createTheme({
        palette: {
            mode,
            background: { default: p["--bg-primary"], paper: p["--bg-secondary"] },
            text: { primary: p["--text-primary"], secondary: p["--text-secondary"], disabled: p["--text-muted"] },
            primary: { main: accent.hex, light: accent.hover, dark: accent.hex, contrastText: accent.contrast },
            success: { main: p["--accent-up"] }, error: { main: p["--accent-down"] },
            warning: { main: p["--accent-gold"] }, divider: p["--border-color"],
        },
        typography: {
            fontFamily: TYPOGRAPHY.fontBody, fontSize: 13,
            h1: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 650, letterSpacing: "-0.02em" },
            h2: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 650, letterSpacing: "-0.02em" },
            h3: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 600, letterSpacing: "-0.01em" },
            h4: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 650 },
            h5: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 600 },
            h6: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 600 },
            body1: { fontFamily: TYPOGRAPHY.fontBody, fontSize: "0.875rem" },
            body2: { fontFamily: TYPOGRAPHY.fontBody, fontSize: "0.8rem", color: p["--text-secondary"] },
            caption: { fontFamily: TYPOGRAPHY.fontMono, fontSize: "0.75rem" },
        },
        shape: { borderRadius: 4 },
        components: {
            MuiCssBaseline: { styleOverrides: { body: { background: p["--bg-primary"] } } },
            MuiCard: { styleOverrides: { root: {
                background: p["--bg-secondary"],
                border: `1px solid ${p["--border-color"]}`, borderRadius: LAYOUT.cardRadius,
                boxShadow: cardShadow, transition: "border-color .15s ease, background-color .15s ease",
                "&:hover": { borderColor: accent.hex, background: p["--bg-elevated"] },
            } } },
            MuiTextField: { styleOverrides: { root: {
                "& .MuiOutlinedInput-root": {
                    color: p["--text-primary"], background: p["--bg-tertiary"], borderRadius: LAYOUT.inputRadius,
                    fontSize: "0.875rem", "& fieldset": { borderColor: p["--border-color"] },
                    "&:hover fieldset": { borderColor: accent.hex },
                    "&.Mui-focused fieldset": { borderColor: accent.hex, borderWidth: "1px" },
                },
                "& .MuiInputLabel-root": { color: p["--text-secondary"], "&.Mui-focused": { color: accent.hex } },
            } } },
            MuiButton: { styleOverrides: {
                root: { borderRadius: LAYOUT.buttonRadius, textTransform: "none", fontWeight: 600, fontSize: "0.825rem", transition: "background-color .15s ease, border-color .15s ease" },
                containedPrimary: { background: accent.hex, color: accent.contrast, boxShadow: "none", "&:hover": { background: accent.hover, boxShadow: "none" } },
                outlinedPrimary: { borderColor: p["--border-color"], color: p["--text-primary"], "&:hover": { borderColor: accent.hex, backgroundColor: accent.muted } },
            } },
            MuiTabs: { styleOverrides: { root: { minHeight: 40 }, indicator: { backgroundColor: accent.hex, height: 2 } } },
            MuiTab: { styleOverrides: { root: { color: p["--text-secondary"], textTransform: "none", fontWeight: 600, minHeight: 40, "&.Mui-selected": { color: accent.hex } } } },
            MuiDivider: { styleOverrides: { root: { borderColor: p["--border-color"] } } },
            MuiDialog: { styleOverrides: { paper: { background: p["--bg-secondary"], border: `1px solid ${p["--border-color"]}`, borderRadius: LAYOUT.cardRadius, boxShadow: "0 12px 36px rgba(0,0,0,.24)" } } },
            MuiTableHead: { styleOverrides: { root: { background: p["--bg-tertiary"] } } },
            MuiTableCell: { styleOverrides: {
                root: { borderColor: p["--border-color"], color: p["--text-primary"], fontSize: "0.78rem", padding: "8px 12px", fontVariantNumeric: "tabular-nums" },
                head: { color: p["--text-secondary"], fontWeight: 650, fontSize: "0.72rem", letterSpacing: ".06em", textTransform: "uppercase" },
            } },
            MuiTableRow: { styleOverrides: { root: { transition: "background .15s ease", "&:hover": { background: p["--bg-hover"] } } } },
            MuiChip: { styleOverrides: { root: { borderRadius: LAYOUT.chipRadius, fontSize: "0.75rem", fontWeight: 600, height: 26 } } },
            MuiTooltip: { styleOverrides: {
                tooltip: { background: p["--bg-tertiary"], border: `1px solid ${p["--border-color"]}`, color: p["--text-primary"], fontSize: "0.75rem", borderRadius: 4 },
                arrow: { color: p["--bg-tertiary"] },
            } },
            MuiMenu: { styleOverrides: { paper: { background: p["--bg-secondary"], border: `1px solid ${p["--border-color"]}`, borderRadius: 4, boxShadow: "0 8px 24px rgba(0,0,0,.18)" } } },
            MuiMenuItem: { styleOverrides: { root: {
                fontSize: "0.875rem", color: p["--text-primary"], "&:hover": { background: p["--bg-hover"] },
                "&.Mui-selected": { background: accent.muted, color: accent.hex },
            } } },
        },
    });
}

function injectCSSVariables(mode, presetKey, accentKey) {
    const root = document.documentElement;
    const palette = getPalette(mode, presetKey);
    const accent = ACCENT_PRESETS[accentKey] || ACCENT_PRESETS.cyan;

    Object.entries(palette).forEach(([key, value]) => root.style.setProperty(key, value));
    root.style.setProperty("--accent-blue", accent.hex);
    root.style.setProperty("--accent-blue-hover", accent.hover);
    root.style.setProperty("--accent-blue-muted", accent.muted);
    root.style.setProperty("--accent-contrast", accent.contrast);
    root.style.setProperty("--glow", accent.glow);
    root.style.setProperty("--accent-gradient", accent.hex);

    root.style.setProperty("--navbar-height", LAYOUT.navbarHeight);
    root.style.setProperty("--sidebar-width", LAYOUT.sidebarWidth);
    root.style.setProperty("--sidebar-collapsed", LAYOUT.sidebarCollapsed);
    root.style.setProperty("--card-radius", LAYOUT.cardRadius);
    root.style.setProperty("--input-radius", LAYOUT.inputRadius);
    root.style.setProperty("--button-radius", LAYOUT.buttonRadius);
    root.style.setProperty("--content-padding", LAYOUT.contentPadding);
    root.style.setProperty("--max-width", LAYOUT.maxWidth);
    root.style.setProperty("--font-body", TYPOGRAPHY.fontBody);
    root.style.setProperty("--font-display", TYPOGRAPHY.fontDisplay);
    root.style.setProperty("--font-mono", TYPOGRAPHY.fontMono);
    root.style.setProperty("--shadow-card", mode === "dark" ? "0 1px 2px rgba(0,0,0,.28)" : "0 1px 2px rgba(15,23,42,.06)");
    root.style.setProperty("--shadow-card-hover", mode === "dark" ? "0 2px 5px rgba(0,0,0,.24)" : "0 2px 5px rgba(15,23,42,.08)");
    root.style.setProperty("--shadow-dropdown", mode === "dark" ? "0 10px 28px rgba(0,0,0,.32)" : "0 10px 28px rgba(15,23,42,.12)");
    root.style.setProperty("--shadow-glow-blue", "none");
    root.style.setProperty("--shadow-glow-green", "none");
    root.style.setProperty("--shadow-glow-red", "none");
}

export const ThemeProvider = ({ children }) => {
    const [systemTheme, setSystemTheme] = useState(getSystemTheme);
    const [themePreference, setThemePreferenceState] = useState(() => {
        const savedPreference = localStorage.getItem("theme_preference");
        if (["light", "dark", "system"].includes(savedPreference)) return savedPreference;
        const legacy = localStorage.getItem("theme");
        return localStorage.getItem("theme_user_set") === "true" && ["light", "dark"].includes(legacy) ? legacy : "system";
    });
    const [colorScheme, setColorSchemeState] = useState(() => {
        const saved = localStorage.getItem("app_color_scheme");
        return THEME_PRESETS[saved] ? saved : "midnight";
    });
    const [accentColor, setAccentColorState] = useState(() => {
        const saved = localStorage.getItem("app_accent_color");
        return ACCENT_PRESETS[saved] ? saved : "cyan";
    });

    const theme = themePreference === "system" ? systemTheme : themePreference;

    useEffect(() => {
        const media = window.matchMedia("(prefers-color-scheme: dark)");
        const onChange = (event) => setSystemTheme(event.matches ? "dark" : "light");
        media.addEventListener?.("change", onChange);
        return () => media.removeEventListener?.("change", onChange);
    }, []);

    useEffect(() => {
        injectCSSVariables(theme, colorScheme, accentColor);
        const root = document.documentElement;
        root.classList.toggle("dark", theme === "dark");
        root.classList.toggle("light", theme === "light");
        root.dataset.theme = theme;
        root.dataset.themePreference = themePreference;
        root.dataset.colorScheme = colorScheme;
        root.style.colorScheme = theme;
        root.style.fontSize = TYPOGRAPHY.baseSize;
        localStorage.setItem("theme", theme);
        localStorage.setItem("theme_preference", themePreference);
        localStorage.setItem("app_color_scheme", colorScheme);
        localStorage.setItem("app_accent_color", accentColor);
    }, [theme, themePreference, colorScheme, accentColor]);

    const setThemeMode = (mode) => {
        if (!["light", "dark", "system"].includes(mode)) return;
        localStorage.setItem("theme_user_set", mode === "system" ? "false" : "true");
        setThemePreferenceState(mode);
    };
    const toggleTheme = () => setThemeMode(theme === "dark" ? "light" : "dark");
    const setColorScheme = (scheme) => THEME_PRESETS[scheme] && setColorSchemeState(scheme);
    const setAccentColor = (accent) => ACCENT_PRESETS[accent] && setAccentColorState(accent);
    const muiTheme = useMemo(() => buildMuiTheme(theme, colorScheme, accentColor), [theme, colorScheme, accentColor]);

    const value = useMemo(() => ({
        theme, themePreference, setThemeMode, toggleTheme,
        colorScheme, setColorScheme, themePresets: THEME_PRESETS,
        accentColor, setAccentColor, accentPresets: ACCENT_PRESETS,
    }), [theme, themePreference, colorScheme, accentColor]);

    return (
        <ThemeContext.Provider value={value}>
            <MuiThemeProvider theme={muiTheme}>
                <CssBaseline />
                {children}
            </MuiThemeProvider>
        </ThemeContext.Provider>
    );
};

export const useTheme = () => {
    const context = useContext(ThemeContext);
    if (!context) throw new Error("useTheme must be used within ThemeProvider");
    return context;
};
