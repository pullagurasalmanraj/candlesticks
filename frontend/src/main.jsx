import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ThemeProvider } from "./context/ThemeContext";
import "./index.css";

// ── Pre-React theme guard ────────────────────────────────────────
// Runs synchronously before React mounts.
// Prevents wrong-theme flash on hard reload and OAuth redirect return.
// ThemeContext will also inject vars on mount — this is just the safety net.
;(function () {
    const preference = localStorage.getItem("theme_preference");
    const legacyTheme = localStorage.getItem("theme");
    const legacyUserSet = localStorage.getItem("theme_user_set") === "true";
    const mode = ["dark", "light", "system"].includes(preference)
        ? preference
        : (legacyUserSet && ["dark", "light"].includes(legacyTheme) ? legacyTheme : "system");
    const theme = mode === "system"
        ? (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light")
        : mode;
    document.documentElement.classList.toggle("dark",  theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
    document.documentElement.style.colorScheme = theme;
})();

// ── Single ThemeProvider — only here, never in App.jsx ──────────
ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
        <ThemeProvider>
            <App />
        </ThemeProvider>
    </React.StrictMode>
);
