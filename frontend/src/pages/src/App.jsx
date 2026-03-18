// src/App.jsx
import React, { useState, Suspense } from "react";
import {
    BrowserRouter as Router,
    Routes,
    Route,
    Navigate,
    useLocation,
    Link,
} from "react-router-dom";



import {
    LayoutDashboard,
    Star,
    Briefcase,
    Settings as SettingsIcon,
    ChevronLeft,
    Moon,
    Sun,
    Brain,
    Cpu,
    LogOut,
    Menu,
} from "lucide-react";



import { ThemeProvider, useTheme } from "./context/ThemeContext";

// Pages
import Dashboard from "./pages/Dashboard";
import Watchlist from "./pages/Watchlist";
import Portfolio from "./pages/Portfolio";
import SettingsPage from "./pages/SettingsPage";
import LstmPredictor from "./pages/LstmPredictor";
import TransformerPredictor from "./pages/TransformerPredictor";
import Login from "./pages/Login";
import LoginSuccess from "./pages/LoginSuccess";
import OptionsTrading from "./pages/OptionsTrading";
import { Activity } from "lucide-react";


// Simple loader for lazy areas
function SkeletonLoader() {
    return (
        <div className="p-8 animate-pulse text-sm text-slate-400">
            <div className="h-5 w-1/4 rounded bg-slate-700/40 mb-4" />
            <div className="h-4 w-2/3 rounded bg-slate-700/40" />
        </div>
    );
}

// ------------------- Protected Route -------------------
function ProtectedRoute({ children }) {
    const token = localStorage.getItem("upstox_access_token");
    const expiry = Number(localStorage.getItem("upstox_token_expiry") || 0);

    if (!token || Date.now() > expiry) {
        localStorage.removeItem("upstox_access_token");
        localStorage.removeItem("upstox_token_expiry");
        return <Navigate to="/login" replace />;
    }

    return children;
}

// ------------------- Sidebar -------------------
function Sidebar({ collapsed, setCollapsed }) {
    const { theme, toggleTheme } = useTheme();
    const isLight = theme === "light";
    const location = useLocation();



    const activePath = location.pathname;

    const navItems = [
        { key: "dashboard", label: "Dashboard", icon: LayoutDashboard, path: "/" },
        { key: "watchlist", label: "Watchlist", icon: Star, path: "/watchlist" },
        { key: "portfolio", label: "Portfolio", icon: Briefcase, path: "/portfolio" },

        // ✅ ADD THIS
        { key: "options", label: "Options Trading", icon: Activity, path: "/options" },

        { key: "settings", label: "Settings", icon: SettingsIcon, path: "/settings" },
    ];


    const aiItems = [
        { key: "lstm", label: "LSTM Predictor", icon: Brain, path: "/lstm" },
        { key: "transformer", label: "Transformer Predictor", icon: Cpu, path: "/transformer" },
    ];

    const handleLogout = () => {
        localStorage.clear();
        window.location.href = "/login";
    };

    return (
        <aside
            className={`h-screen transition-all duration-300 flex flex-col border-r ${collapsed ? "w-20" : "w-64"
                } ${isLight ? "bg-white border-slate-200" : "bg-slate-950 border-slate-800"}`}
        >

            {/* Brand + Collapse */}
            <div className="h-16 px-4 border-b flex items-center justify-between">

                {/* logo hides when collapsed */}
                {!collapsed && (
                    <div className="flex items-center gap-2">
                        <div className="h-8 w-8 rounded-md bg-blue-600 flex items-center justify-center text-xs font-semibold text-white">
                            TD
                        </div>
                        <div className="flex flex-col">
                            <span className="text-sm font-semibold tracking-tight">
                                TradingDesk
                            </span>
                            <span className="text-[11px] text-slate-400">Internal console</span>
                        </div>
                    </div>
                )}

                {/* Collapse / Expand Button */}
                <button
                    onClick={() => setCollapsed(!collapsed)}
                    className="p-2 rounded-md text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800 transition"
                >
                    {collapsed ? <Menu size={18} /> : <ChevronLeft size={18} />}
                </button>
            </div>

            {/* Main nav */}
            <nav className="flex-1 px-3 py-4 space-y-6 overflow-y-auto">
                <div>
                    {!collapsed && (
                        <div className="px-2 mb-2 text-[11px] font-semibold uppercase text-slate-400">
                            Main
                        </div>
                    )}

                    <div className="space-y-1">
                        {navItems.map((item) => {
                            const Icon = item.icon;
                            const isActive = activePath === item.path;

                            return (
                                <Link
                                    key={item.key}
                                    to={item.path}
                                    className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${isActive
                                        ? "bg-blue-600 text-white shadow-sm"
                                        : isLight
                                            ? "text-slate-700 hover:bg-slate-100"
                                            : "text-slate-200 hover:bg-slate-800"
                                        }`}
                                >
                                    <Icon size={18} />
                                    {!collapsed && <span>{item.label}</span>}
                                </Link>
                            );
                        })}
                    </div>
                </div>

                {/* AI Group */}
                <div>
                    {!collapsed && (
                        <div className="px-2 mb-2 text-[11px] font-semibold uppercase text-slate-400">
                            AI & Models
                        </div>
                    )}

                    <div className="space-y-1">
                        {aiItems.map((item) => {
                            const Icon = item.icon;
                            const isActive = activePath === item.path;
                            const isLSTM = item.key === "lstm"; // Identify LSTM Predictor

                            // ---- LSTM opens in a new tab ----
                            if (isLSTM) {
                                return (
                                    <a
                                        key={item.key}
                                        href={item.path}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${isLight
                                            ? "text-slate-700 hover:bg-slate-100"
                                            : "text-slate-200 hover:bg-slate-800"
                                            }`}
                                    >
                                        <Icon size={18} />
                                        {!collapsed && <span>{item.label}</span>}
                                    </a>
                                );
                            }

                            // ---- Other AI pages open normally (SPA) ----
                            return (
                                <Link
                                    key={item.key}
                                    to={item.path}
                                    className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${isActive
                                        ? "bg-slate-900 text-slate-50"
                                        : isLight
                                            ? "text-slate-700 hover:bg-slate-100"
                                            : "text-slate-200 hover:bg-slate-800"
                                        }`}
                                >
                                    <Icon size={18} />
                                    {!collapsed && <span>{item.label}</span>}
                                </Link>
                            );
                        })}
                    </div>
                </div>

            </nav>

            {/* Footer */}
            <div className={`border-t px-4 py-3 flex items-center ${collapsed ? "justify-center" : "justify-between"} text-xs`}>

                {/* Version text - hide when collapsed */}
                {!collapsed && <span className="text-slate-400">v1.0 • Internal</span>}

                {/* Button group */}
                <div className={`flex gap-2 ${collapsed ? "justify-center" : ""}`}>

                    {/* Theme toggle */}
                    <button
                        onClick={toggleTheme}
                        className="p-2 rounded-md border text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                    >
                        {isLight ? <Moon size={15} /> : <Sun size={15} />}
                    </button>

                    {/* Logout */}
                    <button
                        onClick={handleLogout}
                        className={`p-2 rounded-md transition ${collapsed
                            ? "text-red-500 hover:bg-red-500/20"
                            : "flex items-center gap-1 border border-red-200 text-red-600 hover:bg-red-50 dark:border-red-700 dark:hover:bg-red-900/40 px-2 py-1 text-[11px]"
                            }`}
                    >
                        <LogOut size={15} />
                        {!collapsed && "Logout"}
                    </button>
                </div>
            </div>

        </aside>
    );
}

// ------------------- App Shell -------------------
function AppShell() {
    const { theme } = useTheme();
    const isLight = theme === "light";
    const location = useLocation();

    const [collapsed, setCollapsed] = useState(false);

    const isAuthPage =
        location.pathname === "/login" || location.pathname === "/login-success";

    return (
        <div
            className={
                isLight
                    ? "min-h-screen bg-slate-50 text-slate-900"
                    : "min-h-screen bg-slate-950 text-slate-50"
            }
        >
            {isAuthPage ? (
                <div className="min-h-screen flex items-center justify-center">
                    <Suspense fallback={<SkeletonLoader />}>
                        <Routes>
                            <Route path="/login" element={<Login />} />
                            <Route path="/login-success" element={<LoginSuccess />} />
                            <Route path="*" element={<Navigate to="/login" replace />} />
                        </Routes>
                    </Suspense>
                </div>
            ) : (
                <div className="flex h-screen overflow-hidden transition-all duration-300">


                    {/* Collapsible Sidebar */}
                    <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />

                    {/* Main content area */}
                    <div className="flex-1 flex flex-col min-w-0 transition-all duration-300">

                        {/* Top bar */}
                        <header className="h-16 border-b flex items-center justify-between px-6">
                            <div className="flex flex-col">
                                <span className="text-xs uppercase tracking-wide text-slate-400">
                                    Trading console
                                </span>
                                <span className="text-sm font-semibold">
                                    {location.pathname === "/"
                                        ? "Dashboard"
                                        : location.pathname
                                            .replace("/", "")
                                            .replace("-", " ")
                                            .replace(/\b\w/g, (c) => c.toUpperCase())}
                                </span>
                            </div>

                            <div className="flex items-center gap-3">
                                <div className="hidden sm:flex items-center rounded-full border px-3 py-1.5 text-xs text-slate-400">
                                    <span className="h-2 w-2 rounded-full bg-emerald-500 mr-2" />
                                    Live
                                </div>
                                <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-xs font-semibold flex items-center justify-center text-white">
                                    SR
                                </div>
                            </div>
                        </header>


                        {/* Page content */}
                        <main className="flex-1 overflow-y-auto">
                            <Suspense fallback={<SkeletonLoader />}>
                                <Routes>
                                    <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
                                    <Route path="/watchlist" element={<ProtectedRoute><Watchlist /></ProtectedRoute>} />
                                    <Route path="/portfolio" element={<ProtectedRoute><Portfolio /></ProtectedRoute>} />
                                    <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
                                    <Route path="/lstm" element={<ProtectedRoute><LstmPredictor /></ProtectedRoute>} />
                                    <Route path="/transformer" element={<ProtectedRoute><TransformerPredictor /></ProtectedRoute>} />
                                    <Route
                                        path="/options"
                                        element={
                                            <ProtectedRoute>
                                                <OptionsTrading />
                                            </ProtectedRoute>
                                        }
                                    />

                                    <Route path="*" element={<Navigate to="/" replace />} />
                                </Routes>
                            </Suspense>
                        </main>
                    </div>
                </div>
            )}
        </div>
    );
}

// Root App
export default function App() {
    return (
        <ThemeProvider>
            <Router>
                <AppShell />
            </Router>
        </ThemeProvider>
    );
}
