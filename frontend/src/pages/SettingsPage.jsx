import React, { useMemo, useRef, useState } from "react";
import {
    Activity,
    Database,
    HardDriveDownload,
    LogOut,
    Moon,
    Palette,
    RefreshCw,
    Shield,
    Sun,
    Trash2,
    User,
} from "lucide-react";
import { useTheme } from "../context/ThemeContext";
import { loadProfile, saveProfile } from "../utils/profileStorage";
import {
    WATCHLIST_CAP_OPTIONS,
    flattenWatchlistsByCap,
    readPreferredWatchlistCap,
    readStoredWatchlistsByCap,
    savePreferredWatchlistCap,
} from "../utils/watchlistUtils";

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

function getWorkspaceStats() {
    const watchlistsByCap = readStoredWatchlistsByCap();
    const watchlistItems = flattenWatchlistsByCap(watchlistsByCap);
    const selectedInstruments = parseStoredArray("selectedInstruments");
    const cachedPrices = parseStoredObject("lastPrices");
    const activeSubscriptions = parseStoredObject("activeSubscriptions");

    return {
        selectedCount: selectedInstruments.length,
        watchlistCount: watchlistItems.length,
        cachedPriceCount: Object.keys(cachedPrices).length,
        subscriptionCount: Object.keys(activeSubscriptions).length,
    };
}

function cardStyle() {
    return {
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--card-radius)",
        boxShadow: "var(--shadow-card)",
        padding: 24,
    };
}

function labelStyle() {
    return {
        display: "block",
        fontSize: "0.72rem",
        fontWeight: 700,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        marginBottom: 7,
    };
}

function inputStyle() {
    return {
        width: "100%",
        height: 40,
        borderRadius: "var(--input-radius)",
        border: "1px solid var(--border-color)",
        background: "var(--bg-tertiary)",
        color: "var(--text-primary)",
        padding: "0 12px",
        fontSize: "0.88rem",
        fontFamily: "var(--font-body)",
        outline: "none",
        boxSizing: "border-box",
    };
}

function buttonStyle(kind = "primary") {
    if (kind === "danger") {
        return {
            height: 38,
            borderRadius: "var(--button-radius)",
            border: "1px solid rgba(255,82,82,0.35)",
            background: "rgba(255,82,82,0.08)",
            color: "var(--accent-down)",
            padding: "0 14px",
            fontSize: "0.82rem",
            fontWeight: 600,
            fontFamily: "var(--font-body)",
            cursor: "pointer",
        };
    }

    if (kind === "secondary") {
        return {
            height: 38,
            borderRadius: "var(--button-radius)",
            border: "1px solid var(--border-color)",
            background: "transparent",
            color: "var(--text-primary)",
            padding: "0 14px",
            fontSize: "0.82rem",
            fontWeight: 600,
            fontFamily: "var(--font-body)",
            cursor: "pointer",
        };
    }

    return {
        height: 40,
        borderRadius: "var(--button-radius)",
        border: "none",
        background: "var(--accent-blue)",
        color: "#fff",
        padding: "0 16px",
        fontSize: "0.85rem",
        fontWeight: 700,
        fontFamily: "var(--font-body)",
        cursor: "pointer",
        boxShadow: "var(--shadow-glow-blue)",
    };
}

function SectionHeader({ icon: Icon, eyebrow, title, description }) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
            <div style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                background: "var(--accent-blue-muted)",
                color: "var(--accent-blue)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
            }}>
                <Icon size={18} />
            </div>
            <div>
                <div style={{
                    fontSize: "0.68rem",
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "var(--text-muted)",
                    marginBottom: 3,
                }}>
                    {eyebrow}
                </div>
                <div style={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    fontFamily: "var(--font-display)",
                    color: "var(--text-primary)",
                }}>
                    {title}
                </div>
                {description ? (
                    <div style={{
                        fontSize: "0.8rem",
                        color: "var(--text-secondary)",
                        marginTop: 4,
                        lineHeight: 1.5,
                    }}>
                        {description}
                    </div>
                ) : null}
            </div>
        </div>
    );
}

function StatTile({ label, value, tone = "default" }) {
    const toneColor = tone === "success"
        ? "var(--accent-up)"
        : tone === "warning"
            ? "var(--accent-gold)"
            : "var(--text-primary)";

    return (
        <div style={{
            padding: "14px 16px",
            borderRadius: 12,
            background: "var(--bg-tertiary)",
            border: "1px solid var(--border-subtle)",
        }}>
            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 6 }}>
                {label}
            </div>
            <div style={{
                fontSize: "1.1rem",
                fontWeight: 700,
                fontFamily: "var(--font-display)",
                color: toneColor,
            }}>
                {value}
            </div>
        </div>
    );
}

export default function SettingsPage() {
    const { theme, toggleTheme } = useTheme();
    const fileRef = useRef(null);

    const username = localStorage.getItem("user") || "Trader";
    const [form, setForm] = useState(() => buildProfileForm(username));
    const [preferredWatchlistCap, setPreferredWatchlistCap] = useState(() => readPreferredWatchlistCap());
    const [workspaceStats, setWorkspaceStats] = useState(() => getWorkspaceStats());
    const [saved, setSaved] = useState(false);
    const [status, setStatus] = useState("");
    const [photoErr, setPhotoErr] = useState("");

    const tokenExpiry = Number(localStorage.getItem("upstox_token_expiry") || 0);
    const hasBrokerToken = Boolean(localStorage.getItem("upstox_access_token"));
    const isBrokerConnected = hasBrokerToken && tokenExpiry > Date.now();
    const initials = getInitials(form.displayName || username);

    const tokenExpiryLabel = useMemo(() => {
        if (!tokenExpiry) return "Not available";
        return new Intl.DateTimeFormat("en-IN", {
            dateStyle: "medium",
            timeStyle: "short",
        }).format(new Date(tokenExpiry));
    }, [tokenExpiry]);

    const handlePhoto = (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) {
            setPhotoErr("Profile image must be under 2 MB.");
            return;
        }

        setPhotoErr("");
        const reader = new FileReader();
        reader.onload = (loadEvent) => {
            setForm((prev) => ({ ...prev, photo: loadEvent.target.result }));
        };
        reader.readAsDataURL(file);
    };

    const handleSave = () => {
        saveProfile(form);
        savePreferredWatchlistCap(preferredWatchlistCap);
        setSaved(true);
        setStatus("Settings saved.");
        setTimeout(() => setSaved(false), 2000);
    };

    const refreshStats = (message) => {
        setWorkspaceStats(getWorkspaceStats());
        setStatus(message);
    };

    const handleClearWatchlists = () => {
        if (!window.confirm("Clear every saved watchlist bucket?")) return;
        localStorage.removeItem("watchlistsByCap");
        localStorage.removeItem("watchlist");
        refreshStats("Watchlists cleared.");
    };

    const handleClearWorkspace = () => {
        if (!window.confirm("Clear watchlists, selected instruments, and cached prices?")) return;
        localStorage.removeItem("selectedInstruments");
        localStorage.removeItem("watchlistsByCap");
        localStorage.removeItem("watchlist");
        localStorage.removeItem("lastPrices");
        localStorage.removeItem("activeSubscriptions");
        refreshStats("Workspace cache cleared.");
    };

    const handleClearPriceCache = () => {
        localStorage.removeItem("lastPrices");
        refreshStats("Price cache cleared.");
    };

    const handleDisconnectBroker = () => {
        localStorage.removeItem("upstox_access_token");
        localStorage.removeItem("upstox_token_expiry");
        window.location.href = "/brokers";
    };

    const handleSignOut = () => {
        if (!window.confirm("Sign out and clear this local session?")) return;
        localStorage.clear();
        window.location.href = "/login";
    };

    return (
        <div style={{ padding: "28px", maxWidth: "1280px", margin: "0 auto" }}>
            <div style={{
                marginBottom: 24,
                padding: "24px 28px",
                borderRadius: "var(--card-radius)",
                background: "linear-gradient(135deg, var(--bg-secondary), var(--bg-tertiary))",
                border: "1px solid var(--border-color)",
                boxShadow: "var(--shadow-card)",
            }}>
                <div style={{
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "var(--text-muted)",
                    marginBottom: 8,
                }}>
                    Trading Console
                </div>
                <h1 style={{
                    margin: 0,
                    fontSize: "clamp(1.8rem, 3vw, 2.5rem)",
                    fontFamily: "var(--font-display)",
                    color: "var(--text-primary)",
                    letterSpacing: "-0.03em",
                }}>
                    Settings
                </h1>
                <p style={{
                    margin: "10px 0 0",
                    maxWidth: 680,
                    color: "var(--text-secondary)",
                    lineHeight: 1.65,
                    fontSize: "0.92rem",
                }}>
                    Manage your profile, broker session, workspace defaults, and the browser-side
                    data this trading console keeps for watchlists, selections, and cached ticks.
                </p>
            </div>

            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
                gap: 20,
                alignItems: "start",
            }}>
                <section style={cardStyle()}>
                    <SectionHeader
                        icon={User}
                        eyebrow="Account"
                        title="Profile"
                        description="Keep the trader identity used across the UI up to date."
                    />

                    <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
                        <div
                            onClick={() => fileRef.current?.click()}
                            style={{
                                width: 72,
                                height: 72,
                                borderRadius: "50%",
                                background: form.photo
                                    ? "transparent"
                                    : "linear-gradient(135deg, var(--accent-blue), var(--accent-up))",
                                border: "2px solid var(--border-color)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                overflow: "hidden",
                                cursor: "pointer",
                                flexShrink: 0,
                                color: "#fff",
                                fontSize: "1.3rem",
                                fontWeight: 700,
                                fontFamily: "var(--font-display)",
                            }}
                        >
                            {form.photo
                                ? <img src={form.photo} alt="profile" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                                : initials}
                        </div>

                        <div>
                            <div style={{
                                fontSize: "1rem",
                                fontWeight: 700,
                                fontFamily: "var(--font-display)",
                                color: "var(--text-primary)",
                                marginBottom: 4,
                            }}>
                                {form.displayName || username}
                            </div>
                            <div style={{
                                fontSize: "0.78rem",
                                color: "var(--text-muted)",
                                fontFamily: "var(--font-mono)",
                                marginBottom: 10,
                            }}>
                                {username}
                            </div>
                            <button type="button" onClick={() => fileRef.current?.click()} style={buttonStyle("secondary")}>
                                Change photo
                            </button>
                            <input
                                ref={fileRef}
                                type="file"
                                accept="image/*"
                                style={{ display: "none" }}
                                onChange={handlePhoto}
                            />
                            {photoErr ? (
                                <div style={{ marginTop: 8, fontSize: "0.74rem", color: "var(--accent-down)" }}>
                                    {photoErr}
                                </div>
                            ) : null}
                        </div>
                    </div>

                    <div style={{ display: "grid", gap: 14 }}>
                        <div>
                            <label style={labelStyle()}>Display Name</label>
                            <input
                                value={form.displayName}
                                onChange={(event) => setForm((prev) => ({ ...prev, displayName: event.target.value }))}
                                style={inputStyle()}
                                placeholder="Your name"
                            />
                        </div>
                        <div>
                            <label style={labelStyle()}>Email</label>
                            <input
                                value={form.email}
                                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                                style={inputStyle()}
                                placeholder="you@example.com"
                            />
                        </div>
                        <div>
                            <label style={labelStyle()}>Phone</label>
                            <input
                                value={form.phone}
                                onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                                style={inputStyle()}
                                placeholder="+91 9876543210"
                            />
                        </div>
                        <div>
                            <label style={labelStyle()}>Preferred Broker</label>
                            <input
                                value={form.broker}
                                onChange={(event) => setForm((prev) => ({ ...prev, broker: event.target.value }))}
                                style={inputStyle()}
                                placeholder="Upstox"
                            />
                        </div>
                    </div>
                </section>

                <section style={cardStyle()}>
                    <SectionHeader
                        icon={Palette}
                        eyebrow="Workspace"
                        title="Appearance & defaults"
                        description="Tune the dashboard experience without touching backend configuration."
                    />

                    <div style={{
                        padding: "16px",
                        borderRadius: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-subtle)",
                        marginBottom: 16,
                    }}>
                        <div style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 16,
                        }}>
                            <div>
                                <div style={{
                                    fontSize: "0.9rem",
                                    fontWeight: 700,
                                    color: "var(--text-primary)",
                                    marginBottom: 4,
                                }}>
                                    Theme
                                </div>
                                <div style={{
                                    fontSize: "0.78rem",
                                    color: "var(--text-secondary)",
                                    lineHeight: 1.5,
                                }}>
                                    Applied instantly across the app shell and research pages.
                                </div>
                            </div>
                            <button
                                type="button"
                                onClick={toggleTheme}
                                style={{ ...buttonStyle("secondary"), display: "flex", alignItems: "center", gap: 8 }}
                            >
                                {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
                                {theme === "dark" ? "Switch to light" : "Switch to dark"}
                            </button>
                        </div>
                    </div>

                    <div>
                        <label style={labelStyle()}>Preferred Watchlist Bucket</label>
                        <select
                            value={preferredWatchlistCap}
                            onChange={(event) => setPreferredWatchlistCap(event.target.value)}
                            style={inputStyle()}
                        >
                            {WATCHLIST_CAP_OPTIONS.map((option) => (
                                <option key={option.key} value={option.key}>
                                    {option.label}
                                </option>
                            ))}
                        </select>
                        <div style={{ marginTop: 8, fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                            Dashboard and Watchlist reopen on this bucket, and the pages keep it in sync when you switch tabs.
                        </div>
                    </div>

                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: 12,
                        marginTop: 18,
                    }}>
                        <StatTile label="Current Theme" value={theme === "dark" ? "Dark" : "Light"} />
                        <StatTile
                            label="Default Watchlist"
                            value={WATCHLIST_CAP_OPTIONS.find((item) => item.key === preferredWatchlistCap)?.label || "Large Cap"}
                        />
                    </div>
                </section>

                <section style={cardStyle()}>
                    <SectionHeader
                        icon={Activity}
                        eyebrow="Broker"
                        title="Connection status"
                        description="The broker session powers protected routes, live data, and options workflows."
                    />

                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: 12,
                        marginBottom: 16,
                    }}>
                        <StatTile
                            label="Status"
                            value={isBrokerConnected ? "Connected" : "Disconnected"}
                            tone={isBrokerConnected ? "success" : "warning"}
                        />
                        <StatTile label="Token Expiry" value={tokenExpiryLabel} />
                    </div>

                    <div style={{
                        padding: "14px 16px",
                        borderRadius: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-subtle)",
                        marginBottom: 16,
                        fontSize: "0.82rem",
                        color: "var(--text-secondary)",
                        lineHeight: 1.6,
                    }}>
                        If the token is expired, the app redirects back to broker connect.
                        Reconnecting here keeps the trading flow consistent with the existing protected-route setup.
                    </div>

                    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                        <button
                            type="button"
                            onClick={() => { window.location.href = "/brokers"; }}
                            style={{ ...buttonStyle("primary"), display: "flex", alignItems: "center", gap: 8 }}
                        >
                            <RefreshCw size={15} />
                            Open broker connect
                        </button>
                        <button
                            type="button"
                            onClick={handleDisconnectBroker}
                            style={{ ...buttonStyle("secondary"), display: "flex", alignItems: "center", gap: 8 }}
                        >
                            <Shield size={15} />
                            Disconnect session
                        </button>
                    </div>
                </section>

                <section style={cardStyle()}>
                    <SectionHeader
                        icon={Database}
                        eyebrow="Local Data"
                        title="Saved workspace"
                        description="Clean up the browser state that supports watchlists, selected instruments, and cached live prices."
                    />

                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: 12,
                        marginBottom: 18,
                    }}>
                        <StatTile label="Selected Instruments" value={workspaceStats.selectedCount} />
                        <StatTile label="Watchlist Symbols" value={workspaceStats.watchlistCount} />
                        <StatTile label="Cached Live Prices" value={workspaceStats.cachedPriceCount} />
                        <StatTile label="Saved Subscriptions" value={workspaceStats.subscriptionCount} />
                    </div>

                    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                        <button
                            type="button"
                            onClick={handleClearPriceCache}
                            style={{ ...buttonStyle("secondary"), display: "flex", alignItems: "center", gap: 8 }}
                        >
                            <HardDriveDownload size={15} />
                            Clear price cache
                        </button>
                        <button
                            type="button"
                            onClick={handleClearWatchlists}
                            style={{ ...buttonStyle("secondary"), display: "flex", alignItems: "center", gap: 8 }}
                        >
                            <Trash2 size={15} />
                            Clear watchlists
                        </button>
                        <button
                            type="button"
                            onClick={handleClearWorkspace}
                            style={{ ...buttonStyle("danger"), display: "flex", alignItems: "center", gap: 8 }}
                        >
                            <Database size={15} />
                            Reset workspace
                        </button>
                    </div>
                </section>
            </div>

            <div style={{
                ...cardStyle(),
                marginTop: 20,
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 14,
            }}>
                <div>
                    <div style={{
                        fontSize: "0.9rem",
                        fontWeight: 700,
                        color: "var(--text-primary)",
                        marginBottom: 5,
                    }}>
                        Save account and workspace preferences
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                        {status || "Profile details and the default watchlist bucket are stored locally in this browser."}
                    </div>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                    <button type="button" onClick={handleSave} style={buttonStyle("primary")}>
                        {saved ? "Saved" : "Save settings"}
                    </button>
                    <button
                        type="button"
                        onClick={handleSignOut}
                        style={{ ...buttonStyle("danger"), display: "flex", alignItems: "center", gap: 8 }}
                    >
                        <LogOut size={15} />
                        Sign out
                    </button>
                </div>
            </div>
        </div>
    );
}
