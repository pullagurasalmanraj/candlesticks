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
    Activity,
    TrendingUp,
    Wifi,
} from "lucide-react";

// ThemeProvider lives in main.jsx ONLY — never import it here
import { useTheme } from "./context/ThemeContext";
import ProfileDrawer, { Avatar } from "./components/ProfileDrawer";

// Pages
import Dashboard           from "./pages/Dashboard";
import Watchlist           from "./pages/Watchlist";
import Portfolio           from "./pages/Portfolio";
import SettingsPage        from "./pages/SettingsPage";
import LstmPredictor       from "./pages/LstmPredictor";
import TransformerPredictor from "./pages/TransformerPredictor";
import Login               from "./pages/Login";
import LoginSuccess        from "./pages/LoginSuccess";
import OptionsTrading      from "./pages/OptionsTrading";
import BrokersPage         from "./pages/BrokersPage";

// ── Skeleton loader ──────────────────────────────────────────────
function SkeletonLoader() {
    return (
        <div style={{ padding: "2rem" }}>
            <div style={{
                height: 20, width: "25%", borderRadius: 6,
                background: "var(--bg-tertiary)", marginBottom: 12,
                animation: "pulse 1.5s ease-in-out infinite",
            }} />
            <div style={{
                height: 14, width: "50%", borderRadius: 6,
                background: "var(--bg-tertiary)",
                animation: "pulse 1.5s ease-in-out infinite",
            }} />
            <style>{`
                @keyframes pulse {
                    0%,100% { opacity: 1; }
                    50%     { opacity: 0.4; }
                }
            `}</style>
        </div>
    );
}

// ── Route guards ─────────────────────────────────────────────────
function ProtectedRoute({ children }) {
    const user = localStorage.getItem("user");
    if (!user) return <Navigate to="/login" replace />;
    return children;
}

function BrokerProtectedRoute({ children }) {
    const token  = localStorage.getItem("upstox_access_token");
    const expiry = Number(localStorage.getItem("upstox_token_expiry") || 0);
    if (!token || Date.now() > expiry) return <Navigate to="/brokers" replace />;
    return children;
}

// ── Nav config ───────────────────────────────────────────────────
const NAV_MAIN = [
    { key: "dashboard", label: "Dashboard",      icon: LayoutDashboard, path: "/"           },
    { key: "watchlist", label: "Watchlist",       icon: Star,            path: "/watchlist"  },
    { key: "portfolio", label: "Portfolio",       icon: Briefcase,       path: "/portfolio"  },
    { key: "options",   label: "Options Trading", icon: Activity,        path: "/options"    },
    { key: "settings",  label: "Settings",        icon: SettingsIcon,    path: "/settings"   },
];

const NAV_AI = [
    { key: "lstm",        label: "LSTM Predictor",        icon: Brain, path: "/lstm",        newTab: true  },
    { key: "transformer", label: "Transformer Predictor", icon: Cpu,   path: "/transformer", newTab: false },
];

// ── Sidebar ──────────────────────────────────────────────────────
function Sidebar({ collapsed, setCollapsed }) {
    const { theme, toggleTheme } = useTheme();
    const location = useLocation();
    const activePath = location.pathname;

    const handleLogout = () => {
        // Only disconnect broker — keep user session intact
        // User goes back to /brokers to reconnect, not back to login
        localStorage.removeItem("upstox_access_token");
        localStorage.removeItem("upstox_token_expiry");
        window.location.href = "/brokers";
    };

    // Shared nav link style
    const linkStyle = (isActive) => ({
        display:        "flex",
        alignItems:     "center",
        gap:            collapsed ? 0 : 10,
        justifyContent: collapsed ? "center" : "flex-start",
        padding:        collapsed ? "10px" : "9px 12px",
        borderRadius:   8,
        fontSize:       "0.875rem",
        fontFamily:     "var(--font-body)",
        fontWeight:     isActive ? 700 : 600,
        textDecoration: "none",
        transition:     "all 0.15s ease",
        background:     isActive ? "var(--accent-blue)"        : "transparent",
        color:          isActive ? "#ffffff"                   : "var(--text-primary)",
        boxShadow:      isActive ? "var(--shadow-glow-blue)"   : "none",
    });

    return (
        <aside style={{
            width:         collapsed ? "72px" : "240px",
            height:        "100vh",
            flexShrink:    0,
            display:       "flex",
            flexDirection: "column",
            background:    "var(--bg-secondary)",
            borderRight:   "1px solid var(--border-color)",
            transition:    "width 0.25s ease",
            overflow:      "hidden",
        }}>

            {/* ── Brand header ─────────────────────────────── */}
            <div style={{
                height:         "var(--navbar-height)",
                padding:        "0 14px",
                borderBottom:   "1px solid var(--border-color)",
                display:        "flex",
                alignItems:     "center",
                justifyContent: collapsed ? "center" : "space-between",
                flexShrink:     0,
            }}>
                {!collapsed && (
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        {/* Logo mark */}
                        <div style={{
                            width: 32, height: 32, borderRadius: 8,
                            background: "linear-gradient(135deg, var(--accent-blue), var(--accent-up))",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            flexShrink: 0,
                        }}>
                            <TrendingUp size={16} color="#fff" />
                        </div>
                        <div>
                            <div style={{
                                fontSize: "0.875rem", fontWeight: 700,
                                fontFamily: "var(--font-display)",
                                color: "var(--text-primary)", lineHeight: 1.2,
                            }}>
                                TradingDesk
                            </div>
                            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                                Internal console
                            </div>
                        </div>
                    </div>
                )}

                <button
                    onClick={() => setCollapsed(!collapsed)}
                    style={{
                        padding: 6, borderRadius: 6, border: "1px solid var(--border-color)",
                        background: "transparent", cursor: "pointer",
                        color: "var(--text-muted)", display: "flex",
                        transition: "all 0.15s ease",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "var(--bg-tertiary)"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                    {collapsed ? <Menu size={16} /> : <ChevronLeft size={16} />}
                </button>
            </div>

            {/* ── Navigation ───────────────────────────────── */}
            <nav style={{ flex: 1, padding: "16px 10px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 24 }}>

                {/* Main section */}
                <div>
                    {!collapsed && (
                        <div style={{
                            fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em",
                            textTransform: "uppercase", color: "var(--text-muted)",
                            padding: "0 6px", marginBottom: 8,
                        }}>
                            Main
                        </div>
                    )}
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {NAV_MAIN.map(({ key, label, icon: Icon, path }) => {
                            const isActive = activePath === path;
                            return (
                                <Link key={key} to={path} style={linkStyle(isActive)}
                                    onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "var(--bg-tertiary)"; }}
                                    onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
                                >
                                    <Icon size={17} style={{ flexShrink: 0 }} />
                                    {!collapsed && <span>{label}</span>}
                                </Link>
                            );
                        })}
                    </div>
                </div>

                {/* AI section */}
                <div>
                    {!collapsed && (
                        <div style={{
                            fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em",
                            textTransform: "uppercase", color: "var(--text-muted)",
                            padding: "0 6px", marginBottom: 8,
                        }}>
                            AI & Models
                        </div>
                    )}
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {NAV_AI.map(({ key, label, icon: Icon, path, newTab }) => {
                            const isActive = activePath === path;
                            const Tag = newTab ? "a" : Link;
                            const extraProps = newTab
                                ? { href: path, target: "_blank", rel: "noopener noreferrer" }
                                : { to: path };
                            return (
                                <Tag key={key} {...extraProps} style={linkStyle(isActive)}
                                    onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "var(--bg-tertiary)"; }}
                                    onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
                                >
                                    <Icon size={17} style={{ flexShrink: 0 }} />
                                    {!collapsed && <span>{label}</span>}
                                </Tag>
                            );
                        })}
                    </div>
                </div>
            </nav>

            {/* ── Footer ───────────────────────────────────── */}
            <div style={{
                borderTop:      "1px solid var(--border-color)",
                padding:        "12px 10px",
                display:        "flex",
                alignItems:     "center",
                justifyContent: collapsed ? "center" : "space-between",
                gap:            8,
                flexShrink:     0,
            }}>
                {!collapsed && (
                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                        v1.0 • Internal
                    </span>
                )}

                <div style={{ display: "flex", gap: 6 }}>
                    {/* Theme toggle */}
                    <button
                        onClick={toggleTheme}
                        title="Toggle theme"
                        style={{
                            padding: 7, borderRadius: 6,
                            border: "1px solid var(--border-color)",
                            background: "transparent", cursor: "pointer",
                            color: "var(--text-secondary)",
                            display: "flex", transition: "all 0.15s ease",
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = "var(--bg-tertiary)"}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                    >
                        {theme === "light" ? <Moon size={14} /> : <Sun size={14} />}
                    </button>

                    {/* Logout */}
                    <button
                        onClick={handleLogout}
                        title="Logout"
                        style={{
                            padding:      collapsed ? 7 : "7px 10px",
                            borderRadius: 6,
                            border:       "1px solid rgba(255,82,82,0.3)",
                            background:   "transparent",
                            cursor:       "pointer",
                            color:        "var(--accent-down)",
                            display:      "flex", alignItems: "center", gap: 5,
                            fontSize:     "0.75rem", fontWeight: 600,
                            fontFamily:   "var(--font-body)",
                            transition:   "all 0.15s ease",
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = "rgba(255,82,82,0.08)"}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                    >
                        <LogOut size={14} />
                        {!collapsed && "Disconnect"}
                    </button>
                </div>
            </div>
        </aside>
    );
}

// ── Page title helper ────────────────────────────────────────────
function getPageTitle(pathname) {
    const map = {
        "/":           "Dashboard",
        "/watchlist":  "Watchlist",
        "/portfolio":  "Portfolio",
        "/options":    "Options Trading",
        "/settings":   "Settings",
        "/lstm":       "LSTM Predictor",
        "/transformer":"Transformer Predictor",
    };
    return map[pathname] || pathname.replace("/", "").replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

// ── App shell ────────────────────────────────────────────────────
function AppShell() {
    const { theme } = useTheme();
    const location  = useLocation();
    const [collapsed,    setCollapsed]    = useState(false);
    const [profileOpen,  setProfileOpen]  = useState(false);

    // Pages that render WITHOUT the sidebar shell
    const STANDALONE_PATHS = ["/login", "/login-success", "/brokers"];
    const isStandalone = STANDALONE_PATHS.includes(location.pathname);

    const user     = localStorage.getItem("user");

    if (isStandalone) {
        return (
            <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
                <Suspense fallback={<SkeletonLoader />}>
                    <Routes>
                        {/* If already logged in, /login goes straight to /brokers */}
                        <Route
                            path="/login"
                            element={user ? <Navigate to="/brokers" replace /> : <Login />}
                        />
                        <Route path="/login-success" element={<LoginSuccess />} />
                        {/* /brokers needs user session but NOT broker token — it IS the connect page */}
                        <Route
                            path="/brokers"
                            element={<ProtectedRoute><BrokersPage /></ProtectedRoute>}
                        />
                        <Route path="*" element={<Navigate to="/login" replace />} />
                    </Routes>
                </Suspense>
            </div>
        );
    }

    return (
        <div style={{
            display: "flex", height: "100vh", overflow: "hidden",
            background: "var(--bg-primary)",
        }}>
            {/* Sidebar */}
            <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />

            {/* Main area */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>

                {/* ── Top bar ─────────────────────────────── */}
                <header style={{
                    height:        "var(--navbar-height)",
                    flexShrink:    0,
                    borderBottom:  "1px solid var(--border-color)",
                    background:    "var(--bg-secondary)",
                    display:       "flex",
                    alignItems:    "center",
                    justifyContent:"space-between",
                    padding:       "0 24px",
                }}>
                    <div>
                        <div style={{ fontSize: "0.65rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                            Trading Console
                        </div>
                        <div style={{ fontSize: "0.9rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "var(--text-primary)" }}>
                            {getPageTitle(location.pathname)}
                        </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        {/* Live indicator */}
                        <div style={{
                            display: "flex", alignItems: "center", gap: 6,
                            padding: "5px 12px", borderRadius: 999,
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-tertiary)",
                        }}>
                            <Wifi size={12} color="var(--accent-up)" />
                            <span style={{ fontSize: "0.7rem", color: "var(--accent-up)", fontWeight: 600, fontFamily: "var(--font-mono)" }}>
                                LIVE
                            </span>
                        </div>

                        {/* Avatar — opens profile drawer */}
                        <Avatar
                            size={34}
                            onClick={() => setProfileOpen(true)}
                        />
                    </div>
                </header>

                {/* ── Page content ─────────────────────────── */}
                <main style={{ flex: 1, overflowY: "auto", background: "var(--bg-primary)" }}>
                    <Suspense fallback={<SkeletonLoader />}>
                        <Routes>
                            <Route path="/"            element={<ProtectedRoute><BrokerProtectedRoute><Dashboard /></BrokerProtectedRoute></ProtectedRoute>} />
                            <Route path="/watchlist"   element={<ProtectedRoute><BrokerProtectedRoute><Watchlist /></BrokerProtectedRoute></ProtectedRoute>} />
                            <Route path="/portfolio"   element={<ProtectedRoute><BrokerProtectedRoute><Portfolio /></BrokerProtectedRoute></ProtectedRoute>} />
                            <Route path="/settings"    element={<ProtectedRoute><BrokerProtectedRoute><SettingsPage /></BrokerProtectedRoute></ProtectedRoute>} />
                            <Route path="/lstm"        element={<ProtectedRoute><BrokerProtectedRoute><LstmPredictor /></BrokerProtectedRoute></ProtectedRoute>} />
                            <Route path="/transformer" element={<ProtectedRoute><BrokerProtectedRoute><TransformerPredictor /></BrokerProtectedRoute></ProtectedRoute>} />
                            <Route path="/options"     element={<ProtectedRoute><BrokerProtectedRoute><OptionsTrading /></BrokerProtectedRoute></ProtectedRoute>} />
                            <Route path="*"            element={<Navigate to="/" replace />} />
                        </Routes>
                    </Suspense>
                </main>
            </div>

            {/* ── Profile drawer — accessible from top bar avatar ── */}
            <ProfileDrawer
                open={profileOpen}
                onClose={() => setProfileOpen(false)}
            />
        </div>
    );
}

// ── Root ─────────────────────────────────────────────────────────
// ThemeProvider lives in main.jsx only — do NOT add it here again.
// Two ThemeProviders = two separate React contexts = theme changes
// on the login page never reach the main app tree after OAuth redirect.
export default function App() {
    return (
        <Router>
            <AppShell />
        </Router>
    );
}
