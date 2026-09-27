import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ThemeProvider as MuiThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

const ThemeContext = createContext(null);

// Surface presets contain no brand colour. This keeps the accent selector useful
// and lets every preset work in both light and dark modes.
export const THEME_PRESETS = {
    midnight: {
        label: "Midnight",
        description: "Deep ink surfaces with cool blue depth",
        preview: ["#080b14", "#171d2c", "#a78bfa"],
        dark: {
            "--bg-primary": "#080b14", "--bg-secondary": "#0f1421", "--bg-elevated": "#131a29",
            "--bg-tertiary": "#171d2c", "--bg-hover": "#20283a", "--border-color": "#29334a",
            "--border-subtle": "#1b2335", "--text-primary": "#f3f6ff", "--text-secondary": "#a9b3c7",
            "--text-muted": "#6f7b94", "--accent-up": "#32d583", "--accent-down": "#f97066",
            "--accent-gold": "#fdb022", "--surface-glass": "rgba(15,20,33,0.82)",
            "--surface-glass-strong": "rgba(15,20,33,0.94)", "--glow-green": "rgba(50,213,131,0.28)",
            "--glow-red": "rgba(249,112,102,0.28)",
            "--page-gradient": "radial-gradient(circle at 8% 0%, rgba(124,92,255,0.10), transparent 34%), radial-gradient(circle at 92% 8%, rgba(33,181,255,0.08), transparent 30%), #080b14",
        },
        light: {
            "--bg-primary": "#f5f7fb", "--bg-secondary": "#ffffff", "--bg-elevated": "#fbfcff",
            "--bg-tertiary": "#edf1f7", "--bg-hover": "#e4e9f2", "--border-color": "#d5dce8",
            "--border-subtle": "#e8ecf3", "--text-primary": "#172033", "--text-secondary": "#526079",
            "--text-muted": "#8994a8", "--accent-up": "#087f5b", "--accent-down": "#d92d20",
            "--accent-gold": "#b54708", "--surface-glass": "rgba(255,255,255,0.78)",
            "--surface-glass-strong": "rgba(255,255,255,0.94)", "--glow-green": "rgba(8,127,91,0.18)",
            "--glow-red": "rgba(217,45,32,0.18)",
            "--page-gradient": "radial-gradient(circle at 8% 0%, rgba(124,92,255,0.08), transparent 34%), radial-gradient(circle at 92% 8%, rgba(33,181,255,0.07), transparent 30%), #f5f7fb",
        },
    },
    graphite: {
        label: "Graphite",
        description: "Quiet neutral surfaces for focused analysis",
        preview: ["#0d0e11", "#1d2026", "#22c55e"],
        dark: {
            "--bg-primary": "#0d0e11", "--bg-secondary": "#14161a", "--bg-elevated": "#181a1f",
            "--bg-tertiary": "#1d2026", "--bg-hover": "#282c33", "--border-color": "#30343c",
            "--border-subtle": "#22262c", "--text-primary": "#f5f5f4", "--text-secondary": "#b4b4ad",
            "--text-muted": "#74756f", "--accent-up": "#3ddc97", "--accent-down": "#ff6b6b",
            "--accent-gold": "#f4c95d", "--surface-glass": "rgba(20,22,26,0.84)",
            "--surface-glass-strong": "rgba(20,22,26,0.95)", "--glow-green": "rgba(61,220,151,0.25)",
            "--glow-red": "rgba(255,107,107,0.25)",
            "--page-gradient": "radial-gradient(circle at 12% 0%, rgba(255,255,255,0.045), transparent 32%), #0d0e11",
        },
        light: {
            "--bg-primary": "#f7f7f5", "--bg-secondary": "#fefefd", "--bg-elevated": "#ffffff",
            "--bg-tertiary": "#eeeeeb", "--bg-hover": "#e5e5e1", "--border-color": "#d8d8d2",
            "--border-subtle": "#e9e9e5", "--text-primary": "#252622", "--text-secondary": "#5f615a",
            "--text-muted": "#92948b", "--accent-up": "#147d57", "--accent-down": "#c43232",
            "--accent-gold": "#9a6700", "--surface-glass": "rgba(254,254,253,0.80)",
            "--surface-glass-strong": "rgba(254,254,253,0.95)", "--glow-green": "rgba(20,125,87,0.16)",
            "--glow-red": "rgba(196,50,50,0.16)",
            "--page-gradient": "radial-gradient(circle at 12% 0%, rgba(15,23,42,0.035), transparent 32%), #f7f7f5",
        },
    },
    ocean: {
        label: "Ocean",
        description: "Teal-tinted depth with a calm market feel",
        preview: ["#061310", "#112a25", "#2dd4bf"],
        dark: {
            "--bg-primary": "#061310", "--bg-secondary": "#0b1c19", "--bg-elevated": "#0e2420",
            "--bg-tertiary": "#112a25", "--bg-hover": "#183832", "--border-color": "#245047",
            "--border-subtle": "#15352f", "--text-primary": "#ebfffa", "--text-secondary": "#9bc8bd",
            "--text-muted": "#5f887e", "--accent-up": "#34d399", "--accent-down": "#fb7185",
            "--accent-gold": "#fbbf24", "--surface-glass": "rgba(11,28,25,0.84)",
            "--surface-glass-strong": "rgba(11,28,25,0.95)", "--glow-green": "rgba(52,211,153,0.28)",
            "--glow-red": "rgba(251,113,133,0.26)",
            "--page-gradient": "radial-gradient(circle at 10% 0%, rgba(45,212,191,0.11), transparent 34%), radial-gradient(circle at 90% 15%, rgba(14,116,144,0.10), transparent 30%), #061310",
        },
        light: {
            "--bg-primary": "#f1faf7", "--bg-secondary": "#ffffff", "--bg-elevated": "#fbfffd",
            "--bg-tertiary": "#e4f2ee", "--bg-hover": "#d7ebe5", "--border-color": "#c5ddd6",
            "--border-subtle": "#deeee9", "--text-primary": "#12332d", "--text-secondary": "#456c63",
            "--text-muted": "#7fa097", "--accent-up": "#087f5b", "--accent-down": "#d6334c",
            "--accent-gold": "#a15c00", "--surface-glass": "rgba(255,255,255,0.78)",
            "--surface-glass-strong": "rgba(255,255,255,0.94)", "--glow-green": "rgba(8,127,91,0.18)",
            "--glow-red": "rgba(214,51,76,0.18)",
            "--page-gradient": "radial-gradient(circle at 10% 0%, rgba(45,212,191,0.10), transparent 34%), radial-gradient(circle at 90% 15%, rgba(14,116,144,0.07), transparent 30%), #f1faf7",
        },
    },
};

export const ACCENT_PRESETS = {
    cyan: { hex: "#22D3EE", muted: "rgba(34,211,238,0.14)", hover: "#67E8F9", glow: "rgba(34,211,238,0.32)", contrast: "#082f39" },
    emerald: { hex: "#34D399", muted: "rgba(52,211,153,0.14)", hover: "#6EE7B7", glow: "rgba(52,211,153,0.30)", contrast: "#052e24" },
    purple: { hex: "#A78BFA", muted: "rgba(167,139,250,0.14)", hover: "#C4B5FD", glow: "rgba(167,139,250,0.31)", contrast: "#1e1537" },
    amber: { hex: "#FBBF24", muted: "rgba(251,191,36,0.14)", hover: "#FCD34D", glow: "rgba(251,191,36,0.28)", contrast: "#422006" },
    rose: { hex: "#FB7185", muted: "rgba(251,113,133,0.14)", hover: "#FDA4AF", glow: "rgba(251,113,133,0.29)", contrast: "#4c0519" },
};

export const LAYOUT = {
    navbarHeight: "64px", sidebarWidth: "240px", sidebarCollapsed: "72px",
    cardRadius: "16px", inputRadius: "10px", buttonRadius: "10px", chipRadius: "8px",
    contentPadding: "1.5rem", maxWidth: "1440px",
};

export const TYPOGRAPHY = {
    fontBody: "'DM Sans', 'Segoe UI', sans-serif",
    fontDisplay: "'Syne', 'Segoe UI', sans-serif",
    fontMono: "'JetBrains Mono', 'Fira Code', monospace",
    baseSize: "14px", weightNormal: 400, weightMedium: 500, weightSemiBold: 600, weightBold: 700,
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
    const accent = ACCENT_PRESETS[accentKey] || ACCENT_PRESETS.purple;
    const cardShadow = mode === "dark" ? "0 18px 48px rgba(0,0,0,0.22)" : "0 14px 38px rgba(31,41,55,0.08)";

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
            h1: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 700, letterSpacing: "-0.025em" },
            h2: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 700, letterSpacing: "-0.025em" },
            h3: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 650, letterSpacing: "-0.015em" },
            h4: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 650 },
            h5: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 600 },
            h6: { fontFamily: TYPOGRAPHY.fontDisplay, fontWeight: 600 },
            body1: { fontFamily: TYPOGRAPHY.fontBody, fontSize: "0.875rem" },
            body2: { fontFamily: TYPOGRAPHY.fontBody, fontSize: "0.8rem", color: p["--text-secondary"] },
            caption: { fontFamily: TYPOGRAPHY.fontMono, fontSize: "0.75rem" },
        },
        shape: { borderRadius: 12 },
        components: {
            MuiCssBaseline: { styleOverrides: { body: { backgroundImage: p["--page-gradient"], backgroundAttachment: "fixed" } } },
            MuiCard: { styleOverrides: { root: {
                background: `linear-gradient(145deg, ${p["--bg-secondary"]}, ${p["--bg-elevated"]})`,
                border: `1px solid ${p["--border-color"]}`, borderRadius: LAYOUT.cardRadius,
                boxShadow: cardShadow, transition: "transform .2s ease, border-color .2s ease, box-shadow .2s ease",
                "&:hover": { transform: "translateY(-2px)", borderColor: accent.hex, boxShadow: `0 18px 48px ${accent.muted}` },
            } } },
            MuiTextField: { styleOverrides: { root: {
                "& .MuiOutlinedInput-root": {
                    color: p["--text-primary"], background: p["--bg-tertiary"], borderRadius: LAYOUT.inputRadius,
                    fontSize: "0.875rem", "& fieldset": { borderColor: p["--border-color"] },
                    "&:hover fieldset": { borderColor: accent.hex },
                    "&.Mui-focused fieldset": { borderColor: accent.hex, borderWidth: "1.5px" },
                },
                "& .MuiInputLabel-root": { color: p["--text-secondary"], "&.Mui-focused": { color: accent.hex } },
            } } },
            MuiButton: { styleOverrides: {
                root: { borderRadius: LAYOUT.buttonRadius, textTransform: "none", fontWeight: 650, fontSize: "0.875rem", transition: "all .18s ease" },
                containedPrimary: { background: accent.hex, color: accent.contrast, boxShadow: `0 8px 24px ${accent.glow}`, "&:hover": { background: accent.hover, boxShadow: `0 10px 30px ${accent.glow}` } },
                outlinedPrimary: { borderColor: p["--border-color"], color: p["--text-primary"], "&:hover": { borderColor: accent.hex, backgroundColor: accent.muted } },
            } },
            MuiTabs: { styleOverrides: { root: { minHeight: 40 }, indicator: { backgroundColor: accent.hex, height: 2 } } },
            MuiTab: { styleOverrides: { root: { color: p["--text-secondary"], textTransform: "none", fontWeight: 600, minHeight: 40, "&.Mui-selected": { color: accent.hex } } } },
            MuiDivider: { styleOverrides: { root: { borderColor: p["--border-color"] } } },
            MuiDialog: { styleOverrides: { paper: { background: p["--bg-secondary"], border: `1px solid ${p["--border-color"]}`, borderRadius: LAYOUT.cardRadius, boxShadow: cardShadow } } },
            MuiTableHead: { styleOverrides: { root: { background: p["--bg-tertiary"] } } },
            MuiTableCell: { styleOverrides: {
                root: { borderColor: p["--border-color"], color: p["--text-primary"], fontSize: "0.8rem", padding: "10px 14px" },
                head: { color: p["--text-secondary"], fontWeight: 650, fontSize: "0.72rem", letterSpacing: ".06em", textTransform: "uppercase" },
            } },
            MuiTableRow: { styleOverrides: { root: { transition: "background .15s ease", "&:hover": { background: p["--bg-hover"] } } } },
            MuiChip: { styleOverrides: { root: { borderRadius: LAYOUT.chipRadius, fontSize: "0.75rem", fontWeight: 600, height: 26 } } },
            MuiTooltip: { styleOverrides: {
                tooltip: { background: p["--bg-tertiary"], border: `1px solid ${p["--border-color"]}`, color: p["--text-primary"], fontSize: "0.75rem", borderRadius: 8 },
                arrow: { color: p["--bg-tertiary"] },
            } },
            MuiMenu: { styleOverrides: { paper: { background: p["--bg-secondary"], border: `1px solid ${p["--border-color"]}`, borderRadius: 12, boxShadow: cardShadow } } },
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
    const accent = ACCENT_PRESETS[accentKey] || ACCENT_PRESETS.purple;

    Object.entries(palette).forEach(([key, value]) => root.style.setProperty(key, value));
    root.style.setProperty("--accent-blue", accent.hex);
    root.style.setProperty("--accent-blue-hover", accent.hover);
    root.style.setProperty("--accent-blue-muted", accent.muted);
    root.style.setProperty("--accent-contrast", accent.contrast);
    root.style.setProperty("--glow", accent.glow);
    root.style.setProperty("--accent-gradient", `linear-gradient(135deg, ${accent.hex}, ${accent.hover})`);

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
    root.style.setProperty("--shadow-card", mode === "dark" ? "0 18px 48px rgba(0,0,0,.22)" : "0 14px 38px rgba(31,41,55,.08)");
    root.style.setProperty("--shadow-card-hover", `0 18px 48px ${accent.muted}`);
    root.style.setProperty("--shadow-glow-blue", `0 8px 24px ${accent.glow}`);
    root.style.setProperty("--shadow-glow-green", "0 8px 24px var(--glow-green)");
    root.style.setProperty("--shadow-glow-red", "0 8px 24px var(--glow-red)");
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
        return ACCENT_PRESETS[saved] ? saved : "purple";
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
