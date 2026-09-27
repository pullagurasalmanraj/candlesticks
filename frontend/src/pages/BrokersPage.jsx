import React, { useState } from "react";
import { useTheme } from "../context/ThemeContext";
import { TrendingUp, Zap, Shield, ArrowRight, CheckCircle, Lock, Activity, LogOut, User } from "lucide-react";

const BROKERS = [
    {
        name:        "Upstox",
        logo:        "/logos/upstox.png",
        action:      "/auth/login",
        tag:         "Connected",
        tagType:     "live",
        description: "Full-featured trading with real-time data and advanced order types.",
        features:    ["Real-time quotes", "Options chain", "Margin trading"],
        cta:         "Connect Upstox",
        accent:      "#4f9eff",
        available:   true,
    },
    {
        name:        "Algo Trading",
        logo:        "/logos/algo.png",
        action:      "/options",
        tag:         "Beta",
        tagType:     "beta",
        description: "Automated strategy execution with backtesting and live deployment.",
        features:    ["Strategy builder", "Backtesting engine", "Live execution"],
        cta:         "Open Platform",
        accent:      "#00e676",
        available:   true,
    },
    {
        name:        "Zerodha",
        logo:        "/logos/zerodha.png",
        action:      null,
        tag:         "Coming Soon",
        tagType:     "soon",
        description: "India's largest broker — integration in progress.",
        features:    ["Kite API", "Option strategies", "GTT orders"],
        cta:         "Notify Me",
        accent:      "#ffd54f",
        available:   false,
    },
    {
        name:        "Angel One",
        logo:        "/logos/angelone.png",
        action:      null,
        tag:         "Coming Soon",
        tagType:     "soon",
        description: "SmartAPI integration with full order management support.",
        features:    ["SmartAPI", "WebSocket feeds", "Historical data"],
        cta:         "Notify Me",
        accent:      "#ff8a65",
        available:   false,
    },
];

const TAG_STYLES = {
    live: { bg: "rgba(0,230,118,0.12)",  border: "rgba(0,230,118,0.4)",  color: "#00e676" },
    beta: { bg: "rgba(79,158,255,0.12)", border: "rgba(79,158,255,0.4)", color: "#4f9eff" },
    soon: { bg: "rgba(255,255,255,0.05)",border: "var(--border-color)",  color: "var(--text-muted)" },
};

// Stat strip at the top
const STATS = [
    { icon: <Activity size={14} />, label: "Markets Live",   value: "NSE · BSE · MCX"  },
    { icon: <Zap size={14} />,      label: "Avg Latency",    value: "< 12ms"            },
    { icon: <Shield size={14} />,   label: "Security",       value: "256-bit SSL"       },
    { icon: <TrendingUp size={14} />,label: "Uptime",        value: "99.9%"             },
];

export default function BrokersPage() {
    const { theme } = useTheme();
    const [hoveredCard, setHoveredCard] = useState(null);
    const [notified,    setNotified]    = useState({});

    const user     = localStorage.getItem("user") || "User";
    const initials = user.slice(0, 2).toUpperCase();

    const [isUpstoxConnected, setIsUpstoxConnected] = useState(() => {
        return localStorage.getItem("upstox_connected") === "true" || Boolean(localStorage.getItem("upstox_access_token"));
    });

    React.useEffect(() => {
        fetch("/api/auth/status")
            .then(r => r.json())
            .then(data => {
                if (data && data.connected) {
                    localStorage.setItem("upstox_connected", "true");
                    if (!localStorage.getItem("user")) {
                        localStorage.setItem("user", "Trader");
                    }
                    setIsUpstoxConnected(true);
                }
            })
            .catch(() => {});
    }, []);

    // Broker disconnect — clears server tokens and resets local view state
    const handleDisconnect = async () => {
        try {
            await fetch("/api/auth/disconnect", { method: "POST" });
        } catch {}
        localStorage.removeItem("upstox_connected");
        localStorage.removeItem("upstox_access_token");
        localStorage.removeItem("upstox_token_expiry");
        setIsUpstoxConnected(false);
        window.location.reload();
    };

    // Full sign out — wipes everything, shows signup again
    const handleSignOut = () => {
        localStorage.clear();
        window.location.href = "/login";
    };

    const handleAction = (broker) => {
        if (!broker.available) {
            setNotified(p => ({ ...p, [broker.name]: true }));
            return;
        }
        if (broker.name === "Upstox" && isUpstoxConnected) {
            window.location.href = "/";
            return;
        }
        if (broker.action) window.location.href = broker.action;
    };

    return (
        <div style={{
            minHeight:      "100vh",
            background:     "var(--bg-primary)",
            padding:        "0",
            display:        "flex",
            flexDirection:  "column",
        }}>

            {/* ── Hero header ──────────────────────────────── */}
            <div style={{
                padding:    "48px 48px 0",
                maxWidth:   1200,
                width:      "100%",
                margin:     "0 auto",
            }}>
        {/* ── Top user bar ─────────────────────────────── */}
                <div style={{
                    display:        "flex",
                    alignItems:     "center",
                    justifyContent: "space-between",
                    marginBottom:   32,
                    padding:        "12px 16px",
                    borderRadius:   10,
                    background:     "var(--bg-secondary)",
                    border:         "1px solid var(--border-color)",
                }}>
                    {/* User info */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{
                            width: 34, height: 34, borderRadius: "50%",
                            background: "var(--accent-blue-muted)",
                            border: "1px solid var(--accent-blue)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: "0.75rem", fontWeight: 700, color: "var(--accent-blue)",
                            fontFamily: "var(--font-display)", flexShrink: 0,
                        }}>
                            {initials}
                        </div>
                        <div>
                            <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                {user}
                            </div>
                            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                                Signed in
                            </div>
                        </div>
                    </div>

                    {/* Action buttons */}
                    <div style={{ display: "flex", gap: 8 }}>
                        {/* Disconnect broker — keeps account */}
                        <button
                            onClick={handleDisconnect}
                            style={{
                                padding:      "7px 14px",
                                borderRadius: 7,
                                border:       "1px solid var(--border-color)",
                                background:   "transparent",
                                color:        "var(--text-secondary)",
                                fontFamily:   "var(--font-body)",
                                fontSize:     "0.78rem",
                                fontWeight:   500,
                                cursor:       "pointer",
                                display:      "flex", alignItems: "center", gap: 6,
                                transition:   "all 0.15s ease",
                            }}
                            onMouseEnter={e => {
                                e.currentTarget.style.background   = "var(--bg-tertiary)";
                                e.currentTarget.style.borderColor  = "var(--accent-blue)";
                                e.currentTarget.style.color        = "var(--accent-blue)";
                            }}
                            onMouseLeave={e => {
                                e.currentTarget.style.background   = "transparent";
                                e.currentTarget.style.borderColor  = "var(--border-color)";
                                e.currentTarget.style.color        = "var(--text-secondary)";
                            }}
                        >
                            <Activity size={13} />
                            Disconnect Broker
                        </button>

                        {/* Sign Out — full logout, shows signup again */}
                        <button
                            onClick={handleSignOut}
                            style={{
                                padding:      "7px 14px",
                                borderRadius: 7,
                                border:       "1px solid rgba(255,82,82,0.35)",
                                background:   "rgba(255,82,82,0.06)",
                                color:        "var(--accent-down)",
                                fontFamily:   "var(--font-body)",
                                fontSize:     "0.78rem",
                                fontWeight:   600,
                                cursor:       "pointer",
                                display:      "flex", alignItems: "center", gap: 6,
                                transition:   "all 0.15s ease",
                            }}
                            onMouseEnter={e => {
                                e.currentTarget.style.background  = "rgba(255,82,82,0.14)";
                                e.currentTarget.style.borderColor = "rgba(255,82,82,0.6)";
                            }}
                            onMouseLeave={e => {
                                e.currentTarget.style.background  = "rgba(255,82,82,0.06)";
                                e.currentTarget.style.borderColor = "rgba(255,82,82,0.35)";
                            }}
                        >
                            <LogOut size={13} />
                            Sign Out
                        </button>
                    </div>
                </div>

                {/* Breadcrumb */}
                <div style={{
                    display: "flex", alignItems: "center", gap: 6,
                    marginBottom: 20,
                }}>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        TRADINGDESK
                    </span>
                    <span style={{ color: "var(--border-color)" }}>/</span>
                    <span style={{ fontSize: "0.75rem", color: "var(--accent-blue)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                        BROKER CONNECT
                    </span>
                </div>

                <h1 style={{
                    fontFamily:    "var(--font-display)",
                    fontSize:      "clamp(1.8rem, 3vw, 2.6rem)",
                    fontWeight:    700,
                    color:         "var(--text-primary)",
                    letterSpacing: "-0.03em",
                    lineHeight:    1.15,
                    marginBottom:  10,
                }}>
                    Connect your broker.<br />
                    <span style={{ color: "var(--accent-blue)" }}>Start trading.</span>
                </h1>

                <p style={{
                    fontSize:    "0.95rem",
                    color:       "var(--text-secondary)",
                    maxWidth:    520,
                    lineHeight:  1.7,
                    marginBottom: 32,
                }}>
                    Link your brokerage account to unlock real-time data, order execution,
                    and AI-powered analytics — all from one dashboard.
                </p>

                {/* Stats strip */}
                <div style={{
                    display:      "flex",
                    gap:          0,
                    borderRadius: "var(--card-radius)",
                    border:       "1px solid var(--border-color)",
                    background:   "var(--bg-secondary)",
                    overflow:     "hidden",
                    marginBottom: 40,
                    width:        "fit-content",
                }}>
                    {STATS.map(({ icon, label, value }, i) => (
                        <div key={label} style={{
                            padding:     "14px 24px",
                            borderRight: i < STATS.length - 1 ? "1px solid var(--border-color)" : "none",
                            display:     "flex",
                            alignItems:  "center",
                            gap:         10,
                        }}>
                            <span style={{ color: "var(--accent-blue)" }}>{icon}</span>
                            <div>
                                <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                                    {label}
                                </div>
                                <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
                                    {value}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Broker cards ─────────────────────────────── */}
            <div style={{
                padding:   "0 48px 48px",
                maxWidth:  1200,
                width:     "100%",
                margin:    "0 auto",
            }}>
                <div style={{
                    display:             "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                    gap:                 20,
                }}>
                    {BROKERS.map((broker) => {
                        const isHovered  = hoveredCard === broker.name;
                        const tagStyle   = TAG_STYLES[broker.tagType];
                        const isNotified = notified[broker.name];

                        return (
                            <div
                                key={broker.name}
                                onMouseEnter={() => setHoveredCard(broker.name)}
                                onMouseLeave={() => setHoveredCard(null)}
                                style={{
                                    background:    "var(--bg-secondary)",
                                    border:        `1px solid ${isHovered && broker.available ? "var(--accent-blue)" : "var(--border-color)"}`,
                                    borderRadius:  "var(--card-radius)",
                                    padding:       "28px 24px 24px",
                                    display:       "flex",
                                    flexDirection: "column",
                                    gap:           16,
                                    cursor:        broker.available ? "pointer" : "default",
                                    transition:    "border-color 0.16s ease, background-color 0.16s ease",
                                    boxShadow:     "var(--shadow-card)",
                                    transform:     "none",
                                    opacity:       broker.available ? 1 : 0.75,
                                    position:      "relative",
                                    overflow:      "hidden",
                                }}
                            >
                                {/* Institutional accent top edge */}
                                {broker.available && (
                                    <div style={{
                                        position:    "absolute",
                                        top:         0, left: 0, right: 0,
                                        height:      2,
                                        background:  "var(--accent-blue)",
                                        opacity:     isHovered ? 1 : 0.55,
                                        transition:  "opacity 0.2s ease",
                                    }} />
                                )}

                                {/* ── Top row: logo + tag ────────────── */}
                                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
                                    <div style={{
                                        width: 52, height: 52, borderRadius: "var(--card-radius)",
                                        background:  "var(--bg-tertiary)",
                                        border:      "1px solid var(--border-subtle)",
                                        display:     "flex",
                                        alignItems:  "center",
                                        justifyContent: "center",
                                        overflow:    "hidden",
                                    }}>
                                        <img
                                            src={broker.logo}
                                            alt={broker.name}
                                            style={{ width: 34, height: 34, objectFit: "contain" }}
                                            onError={e => {
                                                // Fallback initials if logo missing
                                                e.currentTarget.style.display = "none";
                                                e.currentTarget.parentNode.innerHTML = `<span style="font-family:var(--font-display);font-size:1rem;font-weight:700;color:${broker.accent}">${broker.name.slice(0,2).toUpperCase()}</span>`;
                                            }}
                                        />
                                    </div>

                                    {/* Tag pill */}
                                    <div style={{
                                        padding:      "3px 10px",
                                        borderRadius: 3,
                                        background:   tagStyle.bg,
                                        border:       `1px solid ${tagStyle.border}`,
                                        fontSize:     "0.65rem",
                                        fontWeight:   700,
                                        letterSpacing:"0.06em",
                                        color:        tagStyle.color,
                                        fontFamily:   "var(--font-mono)",
                                        display:      "flex",
                                        alignItems:   "center",
                                        gap:          5,
                                    }}>
                                        {broker.tagType === "live" && (
                                            <span style={{
                                                width: 6, height: 6, borderRadius: "50%",
                                                background: "var(--accent-up)",
                                                boxShadow:  "none",
                                                animation:  "none",
                                                display: "inline-block",
                                            }} />
                                        )}
                                        {broker.tagType === "beta" && (
                                            <Zap size={10} />
                                        )}
                                        {broker.tagType === "soon" && (
                                            <Lock size={9} />
                                        )}
                                        {broker.tag}
                                    </div>
                                </div>

                                {/* ── Broker name + description ───── */}
                                <div>
                                    <div style={{
                                        fontSize:      "1rem",
                                        fontWeight:    700,
                                        fontFamily:    "var(--font-display)",
                                        color:         "var(--text-primary)",
                                        marginBottom:  6,
                                        letterSpacing: "-0.01em",
                                    }}>
                                        {broker.name}
                                    </div>
                                    <div style={{
                                        fontSize:   "0.8rem",
                                        color:      "var(--text-secondary)",
                                        lineHeight: 1.6,
                                    }}>
                                        {broker.description}
                                    </div>
                                </div>

                                {/* ── Feature list ────────────────── */}
                                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                    {broker.features.map(f => (
                                        <div key={f} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                            <CheckCircle size={13} color={broker.available ? broker.accent : "var(--text-muted)"} />
                                            <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                                                {f}
                                            </span>
                                        </div>
                                    ))}
                                </div>

                                {/* ── CTA button ──────────────────── */}
                                <button
                                    onClick={() => handleAction(broker)}
                                    style={{
                                        marginTop:      "auto",
                                        width:          "100%",
                                        height:         42,
                                        borderRadius:   "var(--button-radius)",
                                        border:         broker.available
                                            ? "none"
                                            : "1px solid var(--border-color)",
                                        background:     broker.available
                                            ? (isHovered ? "var(--accent-blue-hover)" : "var(--accent-blue)")
                                            : "var(--bg-tertiary)",
                                        color:          broker.available ? "#fff" : "var(--text-secondary)",
                                        fontFamily:     "var(--font-body)",
                                        fontSize:       "0.875rem",
                                        fontWeight:     600,
                                        cursor:         "pointer",
                                        display:        "flex",
                                        alignItems:     "center",
                                        justifyContent: "center",
                                        gap:            8,
                                        transition:     "all 0.2s ease",
                                        boxShadow:      "none",
                                    }}
                                >
                                    {isNotified ? (
                                        <>
                                            <CheckCircle size={15} />
                                            You'll be notified
                                        </>
                                    ) : (
                                        <>
                                            {broker.name === "Upstox" && isUpstoxConnected ? "Go to Dashboard" : broker.cta}
                                            {broker.available && <ArrowRight size={15} />}
                                        </>
                                    )}
                                </button>
                            </div>
                        );
                    })}
                </div>

                {/* ── Bottom note ──────────────────────────── */}
                <div style={{
                    marginTop:   32,
                    padding:     "16px 20px",
                    borderRadius: "var(--card-radius)",
                    background:  "var(--bg-secondary)",
                    border:      "1px solid var(--border-subtle)",
                    display:     "flex",
                    alignItems:  "center",
                    gap:         10,
                }}>
                    <Shield size={15} color="var(--accent-blue)" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
                        Your credentials are never stored. We use OAuth 2.0 tokens with expiry
                        for all broker connections. Tokens are encrypted and stored only in your
                        browser session.
                    </span>
                </div>
            </div>

            <style>{`
                @keyframes livePulse {
                    0%, 100% { opacity: 1; transform: scale(1);   }
                    50%      { opacity: 0.5; transform: scale(1.4); }
                }
            `}</style>
        </div>
    );
}
