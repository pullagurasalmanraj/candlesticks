import React, { useEffect, useState, useCallback } from "react";
import { useTheme } from "../context/ThemeContext";

export default function MarketBreadthBarometer({ onSelectSymbol, onAddPreset }) {
    const { theme } = useTheme();
    const isDark = theme === "dark";

    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [lastUpdated, setLastUpdated] = useState(null);

    const fetchBreadthData = useCallback(async (isManual = false) => {
        if (isManual) setIsRefreshing(true);
        try {
            const query = isManual ? `?refresh=true&t=${Date.now()}` : "";
            const res = await fetch(`/api/market-breadth${query}`);
            const resData = await res.json();
            if (resData && resData.status === "success") {
                setData(resData);
                setLastUpdated(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
            }
        } catch (err) {
            console.error("Failed to fetch market breadth:", err);
        } finally {
            setLoading(false);
            if (isManual) {
                setTimeout(() => setIsRefreshing(false), 600);
            }
        }
    }, []);

    useEffect(() => {
        fetchBreadthData();
        const interval = setInterval(() => fetchBreadthData(false), 20000); // 20s auto-refresh
        return () => clearInterval(interval);
    }, [fetchBreadthData]);

    const breadth = data?.breadth || { advances: 28, declines: 19, unchanged: 3, total: 50, advancePercent: 56.0, declinePercent: 38.0, adRatio: 1.47 };
    const vix = data?.vix || { level: 11.2, change: 0.44, percent: 4.09, open: 10.76, high: 11.35, low: 9.57, previousClose: 10.76, regime: "LOW_VOL", label: "Low Volatility (Calm & Bullish Bias)", color: "var(--accent-up)" };
    const mood = data?.marketMood || { status: "MILDLY BULLISH", sentiment: "Positive Bias with Selective Participation", color: "var(--accent-up)", icon: "📈" };
    const sectors = data?.sectors || [];

    const presets = [
        { name: "🇮🇳 Nifty 50 Bluechips", symbols: ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC", "LT", "BHARTIARTL", "TATAMOTORS"] },
        { name: "🏦 Bank Leaders", symbols: ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK"] },
        { name: "💻 IT Giants", symbols: ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM"] },
        { name: "💰 PSU & High Dividend", symbols: ["COALINDIA", "NMDC", "ONGC", "IOC", "NTPC", "PFC", "RECLTD"] },
    ];

    return (
        <div style={{
            display: "flex",
            flexDirection: "column",
            gap: 16,
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--card-radius, 14px)",
            padding: "20px",
            boxShadow: isDark ? "0 10px 30px rgba(0, 0, 0, 0.4)" : "0 4px 20px rgba(0, 0, 0, 0.06)",
            width: "100%",
            color: "var(--text-primary)",
            fontFamily: "var(--font-sans, Inter, sans-serif)",
            transition: "background 0.25s ease, border-color 0.25s ease",
        }}>
            {/* ── HEADER ──────────────────────────────────────────────── */}
            <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 12,
                borderBottom: "1px solid var(--border-color)",
                paddingBottom: 16,
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{
                        width: 40, height: 40, borderRadius: 10,
                        background: "rgba(59, 130, 246, 0.12)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: "1.3rem", border: "1px solid rgba(59, 130, 246, 0.3)"
                    }}>
                        🧭
                    </div>
                    <div>
                        <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-blue)" }}>
                            Live Macro Cockpit
                        </div>
                        <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                            Market Breadth & Sector Heat
                        </div>
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    {/* Market Mood Badge */}
                    <div style={{
                        background: isDark ? "rgba(0, 230, 118, 0.12)" : "rgba(0, 168, 84, 0.12)",
                        border: "1px solid var(--border-color)",
                        color: "var(--accent-up)",
                        borderRadius: 8,
                        padding: "6px 14px",
                        fontSize: "0.8rem",
                        fontWeight: 800,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                    }}>
                        <span>{mood.icon}</span>
                        <span>{mood.status}</span>
                    </div>

                    {/* Refresh Button */}
                    <button
                        type="button"
                        onClick={() => fetchBreadthData(true)}
                        disabled={isRefreshing}
                        style={{
                            background: "var(--bg-tertiary)",
                            border: "1px solid var(--border-color)",
                            borderRadius: 8,
                            padding: "6px 12px",
                            cursor: isRefreshing ? "not-allowed" : "pointer",
                            fontSize: "0.76rem",
                            fontWeight: 600,
                            color: "var(--text-primary)",
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            transition: "all 0.2s ease",
                        }}
                        title="Force refresh live quotes"
                    >
                        <span style={{
                            display: "inline-block",
                            animation: isRefreshing ? "spin 0.8s linear infinite" : "none",
                            fontSize: "0.9rem"
                        }}>
                            🔄
                        </span>
                        <span>{isRefreshing ? "Refreshing..." : lastUpdated ? `Updated ${lastUpdated}` : "Refresh"}</span>
                    </button>
                </div>
            </div>

            {/* ── TOP 2-COLUMN KPI: ADVANCES/DECLINES + INDIA VIX ─────── */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: 16,
            }}>
                {/* 1. ADVANCE / DECLINE CARD */}
                <div style={{
                    background: "var(--bg-tertiary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 12,
                    padding: "16px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.05em" }}>
                            🟢/🔴 Advance / Decline Ratio
                        </div>
                        <span style={{
                            fontSize: "0.72rem", fontWeight: 800,
                            color: breadth.adRatio >= 1 ? "var(--accent-up)" : "var(--accent-down)",
                            background: breadth.adRatio >= 1 ? "rgba(0, 230, 118, 0.12)" : "rgba(255, 82, 82, 0.12)",
                            border: `1px solid ${breadth.adRatio >= 1 ? "rgba(0, 230, 118, 0.3)" : "rgba(255, 82, 82, 0.3)"}`,
                            padding: "3px 10px", borderRadius: 6,
                        }}>
                            {breadth.adRatio}x Ratio
                        </span>
                    </div>

                    {/* Big Metric Numbers */}
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                        <div>
                            <span style={{ fontSize: "1.7rem", fontWeight: 900, color: "var(--accent-up)", letterSpacing: "-0.02em" }}>
                                {breadth.advances}
                            </span>
                            <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginLeft: 6, fontWeight: 600 }}>
                                Advances ({breadth.advancePercent}%)
                            </span>
                        </div>
                        <div style={{ textAlign: "right" }}>
                            <span style={{ fontSize: "1.7rem", fontWeight: 900, color: "var(--accent-down)", letterSpacing: "-0.02em" }}>
                                {breadth.declines}
                            </span>
                            <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginLeft: 6, fontWeight: 600 }}>
                                Declines ({breadth.declinePercent}%)
                            </span>
                        </div>
                    </div>

                    {/* Progress Ratio Bar */}
                    <div style={{
                        height: 10,
                        background: "var(--bg-secondary)",
                        borderRadius: 5,
                        overflow: "hidden",
                        display: "flex",
                        border: "1px solid var(--border-color)",
                    }}>
                        <div style={{
                            width: `${breadth.advancePercent}%`,
                            background: "linear-gradient(90deg, #059669, #00E676)",
                            transition: "width 0.6s ease",
                        }} />
                        <div style={{
                            width: `${Math.max(0, 100 - breadth.advancePercent - breadth.declinePercent)}%`,
                            background: "var(--border-color)",
                        }} />
                        <div style={{
                            width: `${breadth.declinePercent}%`,
                            background: "linear-gradient(90deg, #DC2626, #FF5252)",
                            transition: "width 0.6s ease",
                        }} />
                    </div>

                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                        {mood.sentiment}
                    </div>
                </div>

                {/* 2. OFFICIAL NSE INDIA VIX VOLATILITY CARD */}
                <div style={{
                    background: "var(--bg-tertiary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 12,
                    padding: "16px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.05em" }}>
                            📉 India VIX (Market Volatility)
                        </div>
                        <span style={{
                            fontSize: "0.72rem", fontWeight: 800,
                            color: "var(--accent-blue)",
                            background: "rgba(59, 130, 246, 0.12)",
                            border: "1px solid rgba(59, 130, 246, 0.3)",
                            padding: "3px 10px", borderRadius: 6,
                        }}>
                            {vix.regime ? vix.regime.replace("_", " ") : "NORMAL VOL"}
                        </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                            <span style={{ fontSize: "1.8rem", fontWeight: 900, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                                {typeof vix.level === "number" ? vix.level.toFixed(2) : vix.level}
                            </span>
                            <span style={{
                                fontSize: "0.9rem", fontWeight: 800,
                                color: (vix.change ?? 0) >= 0 ? "var(--accent-down)" : "var(--accent-up)"
                            }}>
                                {(vix.change ?? 0) >= 0 ? `▲ +${vix.change}` : `▼ ${vix.change}`} ({vix.percent}%)
                            </span>
                        </div>
                        <span style={{
                            fontSize: "0.68rem", fontWeight: 700, color: "var(--accent-blue)",
                            background: "rgba(59, 130, 246, 0.12)", padding: "2px 8px", borderRadius: 4,
                            border: "1px solid rgba(59, 130, 246, 0.3)"
                        }}>
                            NSE India Live
                        </span>
                    </div>

                    {/* VIX Risk Scale Meter */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{
                            position: "relative",
                            height: 8,
                            background: "linear-gradient(90deg, #10B981 0%, #3B82F6 40%, #F59E0B 75%, #EF4444 100%)",
                            borderRadius: 4,
                        }}>
                            <div style={{
                                position: "absolute",
                                left: `${Math.min(Math.max(((vix.level || 13) / 30) * 100, 5), 95)}%`,
                                top: -3,
                                width: 14,
                                height: 14,
                                borderRadius: "50%",
                                background: "#FFFFFF",
                                border: "2px solid var(--accent-blue)",
                                transform: "translateX(-50%)",
                                boxShadow: "0 0 6px rgba(0,0,0,0.4)",
                            }} />
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 600 }}>
                            <span>&lt;13 Calm</span>
                            <span>13-18 Normal</span>
                            <span>18-24 High</span>
                            <span>&gt;24 Extreme</span>
                        </div>
                    </div>

                    {/* Live OHLC Range Strip from NSE */}
                    {(vix.open || vix.high || vix.low) && (
                        <div style={{
                            display: "flex", justifyContent: "space-between",
                            fontSize: "0.72rem", fontWeight: 700, color: "var(--text-secondary)",
                            background: "var(--bg-secondary)", padding: "6px 10px", borderRadius: 8,
                            border: "1px solid var(--border-color)"
                        }}>
                            <span>O: <strong style={{ color: "var(--text-primary)" }}>{vix.open}</strong></span>
                            <span>H: <strong style={{ color: "var(--accent-up)" }}>{vix.high}</strong></span>
                            <span>L: <strong style={{ color: "var(--accent-down)" }}>{vix.low}</strong></span>
                            <span>Prev: <strong style={{ color: "var(--text-secondary)" }}>{vix.previousClose}</strong></span>
                        </div>
                    )}

                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                        {vix.label}
                    </div>
                </div>
            </div>

            {/* ── SECTOR PERFORMANCE HEATMAP (MONEY FLOW) ─────────────── */}
            <div style={{
                display: "flex",
                flexDirection: "column",
                gap: 12,
                background: "var(--bg-tertiary)",
                border: "1px solid var(--border-color)",
                borderRadius: 12,
                padding: "16px",
            }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                    <div>
                        <div style={{ fontSize: "0.92rem", fontWeight: 800, color: "var(--text-primary)" }}>
                            📊 Sector Heat Ranking (Institutional Money Flow)
                        </div>
                        <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: 2 }}>
                            Ranked from top outperforming sectors to lagging sectors
                        </div>
                    </div>
                    <span style={{ fontSize: "0.7rem", color: "var(--accent-blue)", fontWeight: 700 }}>
                        Live Upstox Quotes
                    </span>
                </div>

                {/* Grid of Sector Performance Cards */}
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
                    gap: 10,
                }}>
                    {sectors.map((sec, idx) => {
                        const isUp = sec.percent >= 0;
                        const barWidth = Math.min(Math.abs(sec.percent) * 35, 100);

                        return (
                            <div
                                key={idx}
                                style={{
                                    background: "var(--bg-secondary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 10,
                                    padding: "10px 12px",
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 6,
                                    position: "relative",
                                    overflow: "hidden",
                                }}
                            >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ fontSize: "1.05rem" }}>{sec.icon}</span>
                                        <span style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--text-primary)" }}>
                                            {sec.name.replace("Nifty ", "")}
                                        </span>
                                    </div>
                                    <span style={{
                                        fontSize: "0.84rem",
                                        fontWeight: 900,
                                        color: isUp ? "var(--accent-up)" : "var(--accent-down)",
                                    }}>
                                        {isUp ? `+${sec.percent}%` : `${sec.percent}%`}
                                    </span>
                                </div>

                                {sec.ltp > 0 && (
                                    <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                                        ₹{sec.ltp.toLocaleString("en-IN")}
                                    </div>
                                )}

                                {/* Micro Visual Bar */}
                                <div style={{ height: 4, background: "var(--border-subtle, rgba(0,0,0,0.1))", borderRadius: 2, overflow: "hidden" }}>
                                    <div style={{
                                        height: "100%",
                                        width: `${barWidth}%`,
                                        background: isUp ? "var(--accent-up)" : "var(--accent-down)",
                                    }} />
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* ── 1-CLICK WATCHLIST PRESETS ────────────────────────────── */}
            <div style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                background: "linear-gradient(135deg, rgba(59,130,246,0.08), rgba(16,185,129,0.08))",
                border: "1px dashed rgba(59,130,246,0.35)",
                borderRadius: 12,
                padding: "16px 18px",
            }}>
                <div style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚡ Quick Watchlist Presets</span>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", fontWeight: 400 }}>
                        — Load curated stock baskets into your working list with 1 click:
                    </span>
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {presets.map((preset, pIdx) => (
                        <button
                            key={pIdx}
                            onClick={() => onAddPreset && onAddPreset(preset.symbols)}
                            style={{
                                background: "var(--bg-secondary)",
                                border: "1px solid var(--border-color)",
                                borderRadius: 8,
                                padding: "6px 12px",
                                fontSize: "0.74rem",
                                fontWeight: 700,
                                color: "var(--text-primary)",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: 6,
                                transition: "all 0.15s ease",
                            }}
                            onMouseEnter={(e) => {
                                e.currentTarget.style.borderColor = "var(--accent-blue)";
                                e.currentTarget.style.background = "rgba(59,130,246,0.15)";
                            }}
                            onMouseLeave={(e) => {
                                e.currentTarget.style.borderColor = "var(--border-color)";
                                e.currentTarget.style.background = "var(--bg-secondary)";
                            }}
                        >
                            <span>{preset.name}</span>
                            <span style={{ fontSize: "0.65rem", background: "var(--accent-blue)", color: "#FFFFFF", borderRadius: 4, padding: "2px 6px", fontWeight: 800 }}>
                                +{preset.symbols.length}
                            </span>
                        </button>
                    ))}
                </div>
            </div>

            {/* CSS Animation Keyframes for Refresh Button */}
            <style>{`
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
}
