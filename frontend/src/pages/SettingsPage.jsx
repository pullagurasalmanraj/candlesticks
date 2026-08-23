// src/pages/SettingsPage.jsx
import React, { useState, useEffect, useMemo, useRef } from "react";
import {
    User,
    Palette,
    Sliders,
    Activity,
    Database,
    Shield,
    Sun,
    Moon,
    Check,
    RefreshCw,
    Download,
    Upload,
    Trash2,
    HardDriveDownload,
    LogOut,
    Zap,
    Bell,
    Globe,
    Lock,
    Unlock,
    Sparkles,
    CheckCircle2,
    AlertCircle,
    Monitor,
    Key,
    Radio,
    ShieldAlert
} from "lucide-react";

import { useTheme, ACCENT_PRESETS } from "../context/ThemeContext";
import { loadProfile, saveProfile } from "../utils/profileStorage";
import {
    WATCHLIST_CAP_OPTIONS,
    flattenWatchlistsByCap,
    readPreferredWatchlistCap,
    readStoredWatchlistsByCap,
    savePreferredWatchlistCap,
} from "../utils/watchlistUtils";

// ── Preset Avatars ───────────────────────────────────────────────
const AVATAR_PRESETS = [
    { id: "bull", emoji: "🐂", bg: "linear-gradient(135deg, #10b981, #059669)", label: "Bull" },
    { id: "bear", emoji: "🐻", bg: "linear-gradient(135deg, #ef4444, #dc2626)", label: "Bear" },
    { id: "eagle", emoji: "🦅", bg: "linear-gradient(135deg, #3b82f6, #1d4ed8)", label: "Eagle" },
    { id: "lion", emoji: "🦁", bg: "linear-gradient(135deg, #f59e0b, #d97706)", label: "Lion" },
    { id: "rocket", emoji: "🚀", bg: "linear-gradient(135deg, #8b5cf6, #6d28d9)", label: "Rocket" },
    { id: "crown", emoji: "👑", bg: "linear-gradient(135deg, #ec4899, #be185d)", label: "Master" },
];

const ACCENT_COLOR_OPTIONS = [
    { id: "cyan", hex: "#00E5FF", label: "Cyan Blue" },
    { id: "emerald", hex: "#10B981", label: "Emerald Green" },
    { id: "purple", hex: "#A855F7", label: "Neon Purple" },
    { id: "amber", hex: "#F59E0B", label: "Amber Gold" },
    { id: "rose", hex: "#F43F5E", label: "Crimson Rose" },
];

function getInitials(name) {
    if (!name) return "??";
    return name.trim().split(/\s+/).map((word) => word[0]).join("").slice(0, 2).toUpperCase();
}

function buildProfileForm(username) {
    const profile = loadProfile();
    return {
        displayName: profile.displayName || username,
        email: profile.email || (username.includes("@") ? username : ""),
        phone: profile.phone || "",
        broker: profile.broker || "Upstox",
        photo: profile.photo || null,
        bio: profile.bio || "Intraday & Swing Trader",
        tradingStyle: profile.tradingStyle || "Price Action",
    };
}

function parseStoredArray(key) {
    try {
        const raw = localStorage.getItem(key);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function parseStoredObject(key) {
    try {
        const raw = localStorage.getItem(key);
        const parsed = raw ? JSON.parse(raw) : {};
        return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
        return {};
    }
}

function getStorageUsageInfo() {
    let totalBytes = 0;
    try {
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            const val = localStorage.getItem(key);
            totalBytes += (key ? key.length : 0) + (val ? val.length : 0);
        }
    } catch {
        totalBytes = 0;
    }
    const kb = (totalBytes / 1024).toFixed(1);
    const maxKb = 5120;
    const pct = Math.min(100, Math.round((totalBytes / (maxKb * 1024)) * 100));

    const watchlistsByCap = readStoredWatchlistsByCap();
    const watchlistItems = flattenWatchlistsByCap(watchlistsByCap);
    const selectedInstruments = parseStoredArray("selectedInstruments");
    const cachedPrices = parseStoredObject("lastPrices");
    const activeSubscriptions = parseStoredObject("activeSubscriptions");

    return {
        totalBytes,
        kb,
        pct,
        selectedCount: selectedInstruments.length,
        watchlistCount: watchlistItems.length,
        cachedPriceCount: Object.keys(cachedPrices).length,
        subscriptionCount: Object.keys(activeSubscriptions).length,
    };
}

export default function SettingsPage() {
    const { theme, toggleTheme, accentColor, setAccentColor } = useTheme();
    const fileRef = useRef(null);
    const importRef = useRef(null);

    const username = localStorage.getItem("user") || "Trader";
    const [activeTab, setActiveTab] = useState("profile");

    // Profile state
    const [form, setForm] = useState(() => buildProfileForm(username));

    // Preference states
    const [preferredWatchlistCap, setPreferredWatchlistCap] = useState(() => readPreferredWatchlistCap());
    const [capitalPreset, setCapitalPreset] = useState(() => localStorage.getItem("default_capital_preset") || "50000");
    const [chartStyle, setChartStyle] = useState(() => localStorage.getItem("default_chart_style") || "candlestick");
    const [densityMode, setDensityMode] = useState(() => localStorage.getItem("layout_density") || "comfortable");
    const [soundEnabled, setSoundEnabled] = useState(() => localStorage.getItem("sound_notifications") !== "false");
    const [autoRefreshSec, setAutoRefreshSec] = useState(() => localStorage.getItem("tick_refresh_sec") || "1");

    // Live Backend Broker Status
    const [brokerConnected, setBrokerConnected] = useState(false);
    const [brokerName, setBrokerName] = useState("Upstox");

    // Console Security PIN State
    const [savedPin, setSavedPin] = useState(() => localStorage.getItem("console_security_pin") || "");
    const [pinInput, setPinInput] = useState("");
    const [pinConfirmInput, setPinConfirmInput] = useState("");
    const [isConsoleLocked, setIsConsoleLocked] = useState(false);
    const [unlockPinInput, setUnlockPinInput] = useState("");
    const [pinError, setPinError] = useState("");

    // Telemetry & Feedback
    const [storageInfo, setStorageInfo] = useState(() => getStorageUsageInfo());
    const [savedToast, setSavedToast] = useState(false);
    const [statusMsg, setStatusMsg] = useState("");
    const [photoErr, setPhotoErr] = useState("");
    const [pingMs, setPingMs] = useState(null);
    const [pinging, setPinging] = useState(false);

    const initials = getInitials(form.displayName || username);

    // Fetch backend broker authentication status on mount
    useEffect(() => {
        fetch("/api/auth/status")
            .then((r) => r.json())
            .then((d) => {
                if (d && d.connected) {
                    setBrokerConnected(true);
                    if (d.broker) setBrokerName(d.broker);
                } else {
                    setBrokerConnected(false);
                }
            })
            .catch(() => setBrokerConnected(false));
    }, []);

    const refreshStats = (msg) => {
        setStorageInfo(getStorageUsageInfo());
        if (msg) {
            setStatusMsg(msg);
            setSavedToast(true);
            setTimeout(() => setSavedToast(false), 3500);
        }
    };

    // Ping API test
    const handlePingServer = async () => {
        setPinging(true);
        const start = performance.now();
        try {
            const res = await fetch("/api/auth/status");
            const duration = Math.round(performance.now() - start);
            if (res.ok) {
                setPingMs(duration);
                refreshStats(`⚡ Server responded in ${duration}ms`);
            } else {
                setPingMs(-1);
                refreshStats("⚠️ Server status non-200");
            }
        } catch {
            setPingMs(-1);
            refreshStats("❌ Ping failed");
        } finally {
            setPinging(false);
        }
    };

    // Security PIN Controls
    const handleSetPin = () => {
        if (pinInput.length !== 4 || !/^\d{4}$/.test(pinInput)) {
            setPinError("Security PIN must be exactly 4 digits.");
            return;
        }
        if (pinInput !== pinConfirmInput) {
            setPinError("PINs do not match. Please re-enter.");
            return;
        }
        setPinError("");
        localStorage.setItem("console_security_pin", pinInput);
        setSavedPin(pinInput);
        setPinInput("");
        setPinConfirmInput("");
        refreshStats("🔒 Console Security PIN configured!");
    };

    const handleRemovePin = () => {
        if (!window.confirm("Remove Security PIN lock?")) return;
        localStorage.removeItem("console_security_pin");
        setSavedPin("");
        setPinInput("");
        setPinConfirmInput("");
        refreshStats("Security PIN removed.");
    };

    const handleUnlockConsole = () => {
        if (unlockPinInput === savedPin) {
            setIsConsoleLocked(false);
            setUnlockPinInput("");
            setPinError("");
        } else {
            setPinError("Incorrect Security PIN.");
        }
    };

    // Handle profile photo upload
    const handlePhotoUpload = (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) {
            setPhotoErr("Profile image must be under 2 MB.");
            return;
        }
        setPhotoErr("");
        const reader = new FileReader();
        reader.onload = (ev) => {
            setForm((prev) => ({ ...prev, photo: ev.target.result }));
        };
        reader.readAsDataURL(file);
    };

    // Save configuration
    const handleSaveAll = () => {
        saveProfile(form);
        savePreferredWatchlistCap(preferredWatchlistCap);
        localStorage.setItem("default_capital_preset", capitalPreset);
        localStorage.setItem("default_chart_style", chartStyle);
        localStorage.setItem("layout_density", densityMode);
        localStorage.setItem("sound_notifications", String(soundEnabled));
        localStorage.setItem("tick_refresh_sec", autoRefreshSec);

        refreshStats("Settings saved successfully.");
    };

    // Export Settings JSON
    const handleExportSettings = () => {
        const payload = {
            version: "2.0",
            exportedAt: new Date().toISOString(),
            profile: form,
            preferences: {
                preferredWatchlistCap,
                capitalPreset,
                chartStyle,
                densityMode,
                accentColor,
                soundEnabled,
                autoRefreshSec,
            },
        };
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `candlesticks_settings_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        refreshStats("Settings exported to JSON.");
    };

    // Import Settings JSON
    const handleImportSettings = (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            try {
                const data = JSON.parse(ev.target.result);
                if (data.profile) {
                    setForm(data.profile);
                    saveProfile(data.profile);
                }
                if (data.preferences) {
                    const p = data.preferences;
                    if (p.preferredWatchlistCap) {
                        setPreferredWatchlistCap(p.preferredWatchlistCap);
                        savePreferredWatchlistCap(p.preferredWatchlistCap);
                    }
                    if (p.capitalPreset) setCapitalPreset(p.capitalPreset);
                    if (p.chartStyle) setChartStyle(p.chartStyle);
                    if (p.densityMode) setDensityMode(p.densityMode);
                    if (p.accentColor) setAccentColor(p.accentColor);
                }
                refreshStats("Settings imported successfully!");
            } catch {
                alert("Invalid settings JSON file.");
            }
        };
        reader.readAsText(file);
    };

    // Actions
    const handleClearPriceCache = () => {
        localStorage.removeItem("lastPrices");
        refreshStats("Live price cache cleared.");
    };

    const handleClearWatchlists = () => {
        if (!window.confirm("Clear all watchlists across small, mid, and large cap buckets?")) return;
        localStorage.removeItem("watchlistsByCap");
        localStorage.removeItem("watchlist");
        refreshStats("Watchlists cleared.");
    };

    const handleClearWorkspace = () => {
        if (!window.confirm("Clear watchlists, selections, and tick cache?")) return;
        localStorage.removeItem("selectedInstruments");
        localStorage.removeItem("watchlistsByCap");
        localStorage.removeItem("watchlist");
        localStorage.removeItem("lastPrices");
        localStorage.removeItem("activeSubscriptions");
        refreshStats("Workspace cache fully reset.");
    };

    const handleDisconnectBroker = () => {
        fetch("/api/auth/disconnect", { method: "POST" })
            .finally(() => {
                localStorage.removeItem("upstox_access_token");
                setBrokerConnected(false);
                refreshStats("Disconnected Upstox Session.");
            });
    };

    const handleSignOut = () => {
        if (!window.confirm("Sign out and clear this trading session?")) return;
        localStorage.clear();
        window.location.href = "/login";
    };

    const tabs = [
        { id: "profile", label: "Profile & Trader ID", icon: User },
        { id: "appearance", label: "Appearance & Theme", icon: Palette },
        { id: "trading", label: "Trading Preferences", icon: Sliders },
        { id: "broker", label: "Broker Connection", icon: Activity },
        { id: "storage", label: "Data & Storage", icon: Database },
        { id: "security", label: "Security & Telemetry", icon: Shield },
    ];

    // If Console Security PIN Screen is Locked
    if (isConsoleLocked) {
        return (
            <div style={{
                maxWidth: 480,
                margin: "80px auto",
                padding: 36,
                borderRadius: 24,
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
                textAlign: "center",
            }}>
                <div style={{
                    width: 64,
                    height: 64,
                    borderRadius: "50%",
                    background: "rgba(0, 229, 255, 0.12)",
                    color: "var(--accent-blue)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    margin: "0 auto 18px",
                }}>
                    <Lock size={32} />
                </div>
                <h2 style={{ margin: 0, fontSize: "1.4rem", fontWeight: 800, color: "var(--text-primary)" }}>
                    Console Security Locked
                </h2>
                <p style={{ margin: "6px 0 20px", fontSize: "0.86rem", color: "var(--text-secondary)" }}>
                    Enter your 4-digit Security PIN to unlock terminal settings.
                </p>

                <input
                    type="password"
                    maxLength={4}
                    value={unlockPinInput}
                    onChange={(e) => setUnlockPinInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleUnlockConsole()}
                    placeholder="••••"
                    style={{
                        width: 160,
                        height: 52,
                        borderRadius: 14,
                        border: "2px solid var(--accent-blue)",
                        background: "var(--bg-tertiary)",
                        color: "var(--text-primary)",
                        fontSize: "1.8rem",
                        fontWeight: 800,
                        letterSpacing: "0.3em",
                        textAlign: "center",
                        outline: "none",
                        marginBottom: 16,
                    }}
                />

                {pinError && <div style={{ color: "#EF4444", fontSize: "0.8rem", marginBottom: 14 }}>{pinError}</div>}

                <button
                    type="button"
                    onClick={handleUnlockConsole}
                    style={{
                        width: "100%",
                        height: 44,
                        borderRadius: 12,
                        border: "none",
                        background: "var(--accent-blue)",
                        color: "#fff",
                        fontSize: "0.9rem",
                        fontWeight: 700,
                        cursor: "pointer",
                        boxShadow: "var(--shadow-glow-blue)",
                    }}
                >
                    Unlock Console
                </button>
            </div>
        );
    }

    return (
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "28px 24px 60px" }}>

            {/* ── Toast Notification Bar ── */}
            {savedToast && (
                <div style={{
                    position: "fixed",
                    bottom: 24,
                    right: 24,
                    zIndex: 9999,
                    background: "rgba(16, 185, 129, 0.95)",
                    backdropFilter: "blur(12px)",
                    color: "#fff",
                    padding: "12px 20px",
                    borderRadius: 12,
                    boxShadow: "0 10px 25px -5px rgba(16, 185, 129, 0.4)",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    fontSize: "0.88rem",
                    fontWeight: 600,
                    animation: "fadeIn 0.2s ease-out",
                }}>
                    <CheckCircle2 size={18} />
                    <span>{statusMsg || "Changes saved!"}</span>
                </div>
            )}

            {/* ── Top Dynamic Header Banner ── */}
            <div style={{
                marginBottom: 24,
                padding: "26px 30px",
                borderRadius: 20,
                background: "linear-gradient(135deg, var(--bg-secondary), var(--bg-tertiary))",
                border: "1px solid var(--border-color)",
                boxShadow: "var(--shadow-card)",
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 20,
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                    <div style={{
                        width: 60,
                        height: 60,
                        borderRadius: "50%",
                        background: form.photo
                            ? "transparent"
                            : "linear-gradient(135deg, var(--accent-blue), #3B82F6)",
                        border: "2px solid var(--border-color)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        overflow: "hidden",
                        fontSize: "1.3rem",
                        fontWeight: 800,
                        color: "#fff",
                        boxShadow: "var(--shadow-glow-blue)",
                        flexShrink: 0,
                    }}>
                        {form.photo ? (
                            <img src={form.photo} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        ) : initials}
                    </div>

                    <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <h1 style={{
                                margin: 0,
                                fontSize: "1.6rem",
                                fontWeight: 800,
                                fontFamily: "var(--font-display)",
                                color: "var(--text-primary)",
                                letterSpacing: "-0.02em",
                            }}>
                                {form.displayName || username}
                            </h1>
                            <span style={{
                                padding: "2px 10px",
                                borderRadius: 20,
                                background: brokerConnected ? "rgba(16,185,129,0.12)" : "rgba(245,158,11,0.12)",
                                color: brokerConnected ? "#10B981" : "#F59E0B",
                                border: brokerConnected ? "1px solid rgba(16,185,129,0.3)" : "1px solid rgba(245,158,11,0.3)",
                                fontSize: "0.72rem",
                                fontWeight: 700,
                                letterSpacing: "0.04em",
                                display: "flex",
                                alignItems: "center",
                                gap: 5,
                            }}>
                                <span style={{
                                    width: 6,
                                    height: 6,
                                    borderRadius: "50%",
                                    background: brokerConnected ? "#10B981" : "#F59E0B"
                                }} />
                                {brokerConnected ? `${brokerName} Live Connected` : "Broker Disconnected"}
                            </span>
                        </div>

                        <p style={{
                            margin: "4px 0 0",
                            fontSize: "0.84rem",
                            color: "var(--text-secondary)",
                        }}>
                            {form.bio} • {brokerName} Account
                        </p>
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    {savedPin && (
                        <button
                            type="button"
                            onClick={() => setIsConsoleLocked(true)}
                            style={{
                                height: 42,
                                padding: "0 16px",
                                borderRadius: 12,
                                border: "1px solid var(--border-color)",
                                background: "var(--bg-primary)",
                                color: "var(--text-primary)",
                                fontSize: "0.82rem",
                                fontWeight: 600,
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: 8,
                            }}
                        >
                            <Lock size={15} style={{ color: "var(--accent-blue)" }} />
                            Lock Console
                        </button>
                    )}

                    <button
                        type="button"
                        onClick={handlePingServer}
                        disabled={pinging}
                        style={{
                            height: 42,
                            padding: "0 16px",
                            borderRadius: 12,
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-primary)",
                            color: "var(--text-primary)",
                            fontSize: "0.82rem",
                            fontWeight: 600,
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                        }}
                    >
                        <Zap size={15} style={{ color: pingMs !== null && pingMs > 0 ? "#10B981" : "inherit" }} />
                        {pinging ? "Pinging..." : pingMs !== null ? `${pingMs} ms` : "Ping Server"}
                    </button>

                    <button
                        type="button"
                        onClick={handleSaveAll}
                        style={{
                            height: 42,
                            padding: "0 22px",
                            borderRadius: 12,
                            border: "none",
                            background: "var(--accent-blue)",
                            color: "#fff",
                            fontSize: "0.85rem",
                            fontWeight: 700,
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            boxShadow: "var(--shadow-glow-blue)",
                        }}
                    >
                        <Check size={16} />
                        Save Settings
                    </button>
                </div>
            </div>

            {/* ── Main Dynamic Settings Layout (Tab Navigation + Card Content) ── */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "260px 1fr",
                gap: 24,
                alignItems: "start",
            }}>
                {/* ── Sidebar Navigation Tabs ── */}
                <nav style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 18,
                    padding: 12,
                    boxShadow: "var(--shadow-card)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                }}>
                    <div style={{
                        padding: "8px 12px 6px",
                        fontSize: "0.68rem",
                        fontWeight: 700,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        color: "var(--text-muted)",
                    }}>
                        Console Settings
                    </div>

                    {tabs.map((t) => {
                        const IconComponent = t.icon;
                        const isActive = activeTab === t.id;
                        return (
                            <button
                                key={t.id}
                                type="button"
                                onClick={() => setActiveTab(t.id)}
                                style={{
                                    width: "100%",
                                    padding: "12px 14px",
                                    borderRadius: 12,
                                    border: isActive ? "1px solid var(--accent-blue-muted)" : "1px solid transparent",
                                    background: isActive ? "var(--accent-blue-muted)" : "transparent",
                                    color: isActive ? "var(--accent-blue)" : "var(--text-secondary)",
                                    fontSize: "0.86rem",
                                    fontWeight: isActive ? 700 : 500,
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 12,
                                    cursor: "pointer",
                                    textAlign: "left",
                                    transition: "all 0.15s ease",
                                }}
                            >
                                <IconComponent size={17} style={{ opacity: isActive ? 1 : 0.7 }} />
                                <span>{t.label}</span>
                            </button>
                        );
                    })}

                    <div style={{ height: 1, background: "var(--border-color)", margin: "8px 0" }} />

                    {/* Storage Quick Meter */}
                    <div style={{
                        padding: "12px 14px",
                        borderRadius: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-subtle)",
                    }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.74rem", color: "var(--text-muted)", marginBottom: 6 }}>
                            <span>Cache Usage</span>
                            <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{storageInfo.kb} KB</span>
                        </div>
                        <div style={{
                            width: "100%",
                            height: 6,
                            borderRadius: 3,
                            background: "var(--border-color)",
                            overflow: "hidden",
                        }}>
                            <div style={{
                                width: `${storageInfo.pct}%`,
                                height: "100%",
                                background: storageInfo.pct > 80 ? "#EF4444" : "var(--accent-blue)",
                                borderRadius: 3,
                                transition: "width 0.3s ease",
                            }} />
                        </div>
                    </div>
                </nav>

                {/* ── Active Tab Panel Content ── */}
                <main style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 20,
                    padding: 30,
                    boxShadow: "var(--shadow-card)",
                    minHeight: 520,
                }}>
                    {/* 👤 TAB 1: PROFILE & IDENTITY */}
                    {activeTab === "profile" && (
                        <div style={{ display: "grid", gap: 24 }}>
                            <div>
                                <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    Profile & Trader Identity
                                </h2>
                                <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                                    Personalize your avatar and trader credentials visible across trading terminals.
                                </p>
                            </div>

                            {/* Photo & Preset Avatars */}
                            <div>
                                <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 10 }}>
                                    Trader Avatar
                                </label>
                                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14 }}>
                                    <div
                                        onClick={() => fileRef.current?.click()}
                                        style={{
                                            width: 76,
                                            height: 76,
                                            borderRadius: "50%",
                                            background: form.photo ? "transparent" : "linear-gradient(135deg, var(--accent-blue), #3B82F6)",
                                            border: "2px dashed var(--accent-blue)",
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            cursor: "pointer",
                                            overflow: "hidden",
                                            fontSize: "1.4rem",
                                            fontWeight: 800,
                                            color: "#fff",
                                            flexShrink: 0,
                                        }}
                                    >
                                        {form.photo ? <img src={form.photo} alt="custom" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : initials}
                                    </div>

                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                        {AVATAR_PRESETS.map((p) => (
                                            <button
                                                key={p.id}
                                                type="button"
                                                onClick={() => setForm((prev) => ({ ...prev, photo: null, displayName: prev.displayName || `${p.label} Trader` }))}
                                                style={{
                                                    width: 44,
                                                    height: 44,
                                                    borderRadius: 12,
                                                    background: p.bg,
                                                    border: "none",
                                                    fontSize: "1.2rem",
                                                    cursor: "pointer",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "center",
                                                    boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
                                                }}
                                                title={p.label}
                                            >
                                                {p.emoji}
                                            </button>
                                        ))}
                                    </div>

                                    <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handlePhotoUpload} />
                                    <button type="button" onClick={() => fileRef.current?.click()} style={{ padding: "8px 14px", borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", fontSize: "0.8rem", cursor: "pointer" }}>
                                        Upload custom photo
                                    </button>
                                </div>
                                {photoErr && <div style={{ fontSize: "0.75rem", color: "#EF4444", marginTop: 6 }}>{photoErr}</div>}
                            </div>

                            {/* Form Input Grid */}
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
                                <div>
                                    <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 6 }}>Display Name</label>
                                    <input value={form.displayName} onChange={(e) => setForm((prev) => ({ ...prev, displayName: e.target.value }))} style={{ width: "100%", height: 42, borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", padding: "0 12px", outline: "none" }} />
                                </div>
                                <div>
                                    <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 6 }}>Email</label>
                                    <input value={form.email} onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))} style={{ width: "100%", height: 42, borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", padding: "0 12px", outline: "none" }} />
                                </div>
                                <div>
                                    <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 6 }}>Phone Number</label>
                                    <input value={form.phone} onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))} style={{ width: "100%", height: 42, borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", padding: "0 12px", outline: "none" }} placeholder="+91 9876543210" />
                                </div>
                                <div>
                                    <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 6 }}>Trading Style</label>
                                    <input value={form.tradingStyle} onChange={(e) => setForm((prev) => ({ ...prev, tradingStyle: e.target.value }))} style={{ width: "100%", height: 42, borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", padding: "0 12px", outline: "none" }} placeholder="Intraday / Swing / Scalper" />
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 🎨 TAB 2: APPEARANCE & THEME */}
                    {activeTab === "appearance" && (
                        <div style={{ display: "grid", gap: 24 }}>
                            <div>
                                <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    Appearance & Theme Studio
                                </h2>
                                <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                                    Customize visual themes, color accents, and layout density in real time.
                                </p>
                            </div>

                            {/* Dark/Light Mode Switch */}
                            <div style={{ padding: 18, borderRadius: 14, background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <div>
                                    <div style={{ fontSize: "0.92rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
                                        Theme Mode
                                    </div>
                                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                        Currently active: <strong>{theme === "dark" ? "Dark Cyber Mode" : "Light Mode"}</strong>
                                    </div>
                                </div>
                                <button type="button" onClick={toggleTheme} style={{ padding: "10px 18px", borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-primary)", color: "var(--text-primary)", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                                    {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                                    {theme === "dark" ? "Switch to Light" : "Switch to Dark"}
                                </button>
                            </div>

                            {/* Primary Accent Picker */}
                            <div>
                                <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase" }}>
                                    Terminal Accent Color
                                </label>
                                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                                    {ACCENT_COLOR_OPTIONS.map((c) => (
                                        <button
                                            key={c.id}
                                            type="button"
                                            onClick={() => setAccentColor(c.id)}
                                            style={{
                                                padding: "10px 16px",
                                                borderRadius: 12,
                                                border: accentColor === c.id ? `2px solid ${c.hex}` : "1px solid var(--border-color)",
                                                background: "var(--bg-tertiary)",
                                                color: "var(--text-primary)",
                                                fontSize: "0.82rem",
                                                fontWeight: 600,
                                                cursor: "pointer",
                                                display: "flex",
                                                alignItems: "center",
                                                gap: 8,
                                                boxShadow: accentColor === c.id ? `0 0 14px ${c.hex}40` : "none",
                                            }}
                                        >
                                            <span style={{ width: 14, height: 14, borderRadius: "50%", background: c.hex }} />
                                            {c.label}
                                            {accentColor === c.id && <Check size={14} style={{ color: c.hex }} />}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Density Layout */}
                            <div>
                                <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 10, textTransform: "uppercase" }}>
                                    Layout Density
                                </label>
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
                                    {["comfortable", "compact"].map((mode) => (
                                        <button
                                            key={mode}
                                            type="button"
                                            onClick={() => setDensityMode(mode)}
                                            style={{
                                                padding: 14,
                                                borderRadius: 12,
                                                border: densityMode === mode ? "2px solid var(--accent-blue)" : "1px solid var(--border-color)",
                                                background: "var(--bg-tertiary)",
                                                color: "var(--text-primary)",
                                                textAlign: "left",
                                                cursor: "pointer",
                                            }}
                                        >
                                            <div style={{ fontWeight: 700, fontSize: "0.88rem", textTransform: "capitalize" }}>{mode} Mode</div>
                                            <div style={{ fontSize: "0.76rem", color: "var(--text-secondary)", marginTop: 4 }}>
                                                {mode === "comfortable" ? "Balanced spacing for widescreen monitors" : "Higher data density for multi-chart view"}
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ⚡ TAB 3: TRADING PREFERENCES */}
                    {activeTab === "trading" && (
                        <div style={{ display: "grid", gap: 24 }}>
                            <div>
                                <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    Trading Preferences & Calculator Defaults
                                </h2>
                                <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                                    Set default capital presets, watchlist buckets, and tick streaming speeds.
                                </p>
                            </div>

                            {/* Default Capital Preset for Margin Calculator */}
                            <div>
                                <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase" }}>
                                    Intraday Calculator Capital Preset
                                </label>
                                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                                    {["5000", "10000", "25000", "50000", "100000"].map((amt) => (
                                        <button
                                            key={amt}
                                            type="button"
                                            onClick={() => setCapitalPreset(amt)}
                                            style={{
                                                padding: "10px 18px",
                                                borderRadius: 10,
                                                border: capitalPreset === amt ? "2px solid var(--accent-blue)" : "1px solid var(--border-color)",
                                                background: capitalPreset === amt ? "var(--accent-blue-muted)" : "var(--bg-tertiary)",
                                                color: capitalPreset === amt ? "var(--accent-blue)" : "var(--text-primary)",
                                                fontWeight: 700,
                                                fontSize: "0.85rem",
                                                cursor: "pointer",
                                            }}
                                        >
                                            ₹{(Number(amt) / 1000).toFixed(0)}k Capital
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Default Watchlist Market Cap */}
                            <div>
                                <label style={{ display: "block", fontSize: "0.74rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase" }}>
                                    Default Watchlist Market Cap Bucket
                                </label>
                                <select
                                    value={preferredWatchlistCap}
                                    onChange={(e) => setPreferredWatchlistCap(e.target.value)}
                                    style={{ width: "100%", height: 42, borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", padding: "0 12px" }}
                                >
                                    {WATCHLIST_CAP_OPTIONS.map((opt) => (
                                        <option key={opt.key} value={opt.key}>{opt.label}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Notification sound toggle */}
                            <div style={{ padding: 16, borderRadius: 12, background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <div>
                                    <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 2 }}>
                                        Audio Ticks & Order Alerts
                                    </div>
                                    <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                                        Play subtle audio chime when key price alerts trigger.
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setSoundEnabled((prev) => !prev)}
                                    style={{
                                        padding: "8px 16px",
                                        borderRadius: 10,
                                        border: "1px solid var(--border-color)",
                                        background: soundEnabled ? "var(--accent-blue)" : "var(--bg-primary)",
                                        color: soundEnabled ? "#fff" : "var(--text-muted)",
                                        fontWeight: 700,
                                        cursor: "pointer",
                                    }}
                                >
                                    {soundEnabled ? "Enabled" : "Muted"}
                                </button>
                            </div>
                        </div>
                    )}

                    {/* 🔌 TAB 4: BROKER CONNECTION */}
                    {activeTab === "broker" && (
                        <div style={{ display: "grid", gap: 24 }}>
                            <div>
                                <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    Broker API Connection
                                </h2>
                                <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                                    Live authentication status powered by Upstox OAuth 2.0.
                                </p>
                            </div>

                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
                                <div style={{ padding: 18, borderRadius: 14, background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)" }}>
                                    <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginBottom: 6 }}>Connection Status</div>
                                    <div style={{ fontSize: "1.2rem", fontWeight: 800, color: brokerConnected ? "#10B981" : "#F59E0B", display: "flex", alignItems: "center", gap: 8 }}>
                                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: brokerConnected ? "#10B981" : "#F59E0B" }} />
                                        {brokerConnected ? `${brokerName} Live Connected` : "Broker Disconnected"}
                                    </div>
                                </div>
                                <div style={{ padding: 18, borderRadius: 14, background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)" }}>
                                    <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginBottom: 6 }}>Session Authentication</div>
                                    <div style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                        {brokerConnected ? "Active & Valid (Backend Token)" : "Requires Re-auth"}
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                                <button type="button" onClick={() => { window.location.href = "/brokers"; }} style={{ padding: "12px 20px", borderRadius: 12, border: "none", background: "var(--accent-blue)", color: "#fff", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                                    <RefreshCw size={16} /> Re-authenticate Upstox API
                                </button>
                                <button type="button" onClick={handleDisconnectBroker} style={{ padding: "12px 20px", borderRadius: 12, border: "1px solid rgba(239, 68, 68, 0.4)", background: "rgba(239, 68, 68, 0.1)", color: "#EF4444", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                                    <Shield size={16} /> Disconnect Broker Session
                                </button>
                            </div>
                        </div>
                    )}

                    {/* 💾 TAB 5: DATA & STORAGE */}
                    {activeTab === "storage" && (
                        <div style={{ display: "grid", gap: 24 }}>
                            <div>
                                <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    Data & Workspace Sentinel
                                </h2>
                                <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                                    Export your workspace configuration to JSON or clear local tick caches.
                                </p>
                            </div>

                            {/* Storage Gauge */}
                            <div style={{ padding: 20, borderRadius: 16, background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: "0.88rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    <span>Browser Storage Capacity</span>
                                    <span>{storageInfo.kb} KB used ({storageInfo.pct}%)</span>
                                </div>
                                <div style={{ width: "100%", height: 10, borderRadius: 5, background: "var(--border-color)", overflow: "hidden", marginBottom: 16 }}>
                                    <div style={{ width: `${storageInfo.pct}%`, height: "100%", background: "var(--accent-blue)", borderRadius: 5 }} />
                                </div>
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, textAlign: "center" }}>
                                    <div>
                                        <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-primary)" }}>{storageInfo.watchlistCount}</div>
                                        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Watchlist Stocks</div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-primary)" }}>{storageInfo.selectedCount}</div>
                                        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Active Instruments</div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-primary)" }}>{storageInfo.cachedPriceCount}</div>
                                        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Cached Ticks</div>
                                    </div>
                                    <div>
                                        <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-primary)" }}>{storageInfo.subscriptionCount}</div>
                                        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>WS Feeds</div>
                                    </div>
                                </div>
                            </div>

                            {/* Export / Import JSON */}
                            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                                <button type="button" onClick={handleExportSettings} style={{ padding: "12px 20px", borderRadius: 12, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                                    <Download size={16} /> Export Settings (.json)
                                </button>
                                <button type="button" onClick={() => importRef.current?.click()} style={{ padding: "12px 20px", borderRadius: 12, border: "1px solid var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                                    <Upload size={16} /> Import Settings (.json)
                                </button>
                                <input ref={importRef} type="file" accept=".json" style={{ display: "none" }} onChange={handleImportSettings} />
                            </div>

                            {/* Danger zone */}
                            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 10 }}>
                                <button type="button" onClick={handleClearPriceCache} style={{ padding: "10px 16px", borderRadius: 10, border: "1px solid var(--border-color)", background: "transparent", color: "var(--text-secondary)", fontSize: "0.82rem", cursor: "pointer" }}>
                                    Clear Live Ticks
                                </button>
                                <button type="button" onClick={handleClearWatchlists} style={{ padding: "10px 16px", borderRadius: 10, border: "1px solid var(--border-color)", background: "transparent", color: "var(--text-secondary)", fontSize: "0.82rem", cursor: "pointer" }}>
                                    Clear Watchlists
                                </button>
                                <button type="button" onClick={handleClearWorkspace} style={{ padding: "10px 16px", borderRadius: 10, border: "1px solid rgba(239,68,68,0.4)", background: "rgba(239,68,68,0.08)", color: "#EF4444", fontSize: "0.82rem", fontWeight: 700, cursor: "pointer" }}>
                                    Factory Reset Workspace
                                </button>
                            </div>
                        </div>
                    )}

                    {/* 🔒 TAB 6: SECURITY & TELEMETRY */}
                    {activeTab === "security" && (
                        <div style={{ display: "grid", gap: 24 }}>
                            <div>
                                <h2 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    Security & Terminal Lock Layer
                                </h2>
                                <p style={{ margin: "4px 0 0", fontSize: "0.84rem", color: "var(--text-secondary)" }}>
                                    Set up a 4-digit Security PIN to lock the terminal console.
                                </p>
                            </div>

                            {/* Console PIN Config */}
                            <div style={{ padding: 20, borderRadius: 16, background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                                    <Key size={22} style={{ color: "var(--accent-blue)" }} />
                                    <div>
                                        <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                            4-Digit Console Security PIN
                                        </div>
                                        <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                                            {savedPin ? "PIN is active. Your terminal can be locked anytime." : "No Security PIN set. Enter a 4-digit PIN to lock your session."}
                                        </div>
                                    </div>
                                </div>

                                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                                    <input
                                        type="password"
                                        maxLength={4}
                                        value={pinInput}
                                        onChange={(e) => setPinInput(e.target.value)}
                                        placeholder="New PIN (4 digits)"
                                        style={{ width: 150, height: 40, borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-primary)", color: "var(--text-primary)", padding: "0 12px", outline: "none", fontSize: "1rem", letterSpacing: "0.2em", textAlign: "center" }}
                                    />
                                    <input
                                        type="password"
                                        maxLength={4}
                                        value={pinConfirmInput}
                                        onChange={(e) => setPinConfirmInput(e.target.value)}
                                        placeholder="Confirm PIN"
                                        style={{ width: 150, height: 40, borderRadius: 10, border: "1px solid var(--border-color)", background: "var(--bg-primary)", color: "var(--text-primary)", padding: "0 12px", outline: "none", fontSize: "1rem", letterSpacing: "0.2em", textAlign: "center" }}
                                    />
                                    <button
                                        type="button"
                                        onClick={handleSetPin}
                                        style={{ height: 40, padding: "0 18px", borderRadius: 10, border: "none", background: "var(--accent-blue)", color: "#fff", fontWeight: 700, cursor: "pointer" }}
                                    >
                                        Save PIN
                                    </button>

                                    {savedPin && (
                                        <button
                                            type="button"
                                            onClick={handleRemovePin}
                                            style={{ height: 40, padding: "0 14px", borderRadius: 10, border: "1px solid rgba(239,68,68,0.4)", background: "transparent", color: "#EF4444", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer" }}
                                        >
                                            Remove PIN
                                        </button>
                                    )}
                                </div>
                                {pinError && <div style={{ fontSize: "0.78rem", color: "#EF4444", marginTop: 8 }}>{pinError}</div>}
                            </div>

                            {/* Session Security Details */}
                            <div style={{ padding: 18, borderRadius: 14, background: "var(--bg-tertiary)", border: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", gap: 14 }}>
                                <Lock size={24} style={{ color: "var(--accent-blue)" }} />
                                <div>
                                    <div style={{ fontSize: "0.92rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                        Fernet 256-bit Encryption
                                    </div>
                                    <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: 2 }}>
                                        Upstox OAuth Bearer tokens are stored with symmetric Fernet 256-bit encryption on disk.
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: "flex", gap: 12 }}>
                                <button type="button" onClick={handleSignOut} style={{ padding: "12px 22px", borderRadius: 12, border: "none", background: "#EF4444", color: "#fff", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                                    <LogOut size={16} /> Sign Out Session
                                </button>
                            </div>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
}
