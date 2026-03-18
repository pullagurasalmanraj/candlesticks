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
    const saved  = localStorage.getItem("theme");
    const theme  = (saved === "dark" || saved === "light")
        ? saved
        : window.matchMedia("(prefers-color-scheme: light)").matches
            ? "light"
            : "dark";
    document.documentElement.classList.toggle("dark",  theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
    if (!saved) localStorage.setItem("theme", theme);
})();

// ── Single ThemeProvider — only here, never in App.jsx ──────────
ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
        <ThemeProvider>
            <App />
        </ThemeProvider>
    </React.StrictMode>
);
