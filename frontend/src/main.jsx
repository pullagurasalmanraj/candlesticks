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
    const saved   = localStorage.getItem("theme");
    const userSet = localStorage.getItem("theme_user_set");
    const theme   = (userSet === "true" && (saved === "dark" || saved === "light"))
        ? saved
        : "light";
    document.documentElement.classList.toggle("dark",  theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
    if (!userSet) localStorage.setItem("theme", theme);
})();

// ── Single ThemeProvider — only here, never in App.jsx ──────────
ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
        <ThemeProvider>
            <App />
        </ThemeProvider>
    </React.StrictMode>
);
