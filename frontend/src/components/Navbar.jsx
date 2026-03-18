import { useState, useRef, useEffect } from "react";
import { useTheme } from "../context/ThemeContext";
import {
    TrendingUp, BarChart2, Brain, LayoutDashboard,
    ChevronDown, Activity, Zap, Database,
    Sun, Moon, ArrowRight, Cpu, FlaskConical,
    LineChart, Shield, Wifi
} from "lucide-react";

// ── Mega menu content — sourced directly from app.py ────────────
const MENU_SECTIONS = [
    {
        key:   "market",
        label: "Market Data",
        icon:  <Activity size={15} />,
        description: "Live feeds via Upstox v2/v3",
        cols: [
            {
                title: "Live Indices",
                items: [
                    { label: "Nifty 50",     sub: "NSE_INDEX · Real-time LTP"    },
                    { label: "Bank Nifty",   sub: "NSE_INDEX · Live ticks"       },
                    { label: "Sensex",       sub: "BSE_INDEX · Live ticks"       },
                    { label: "Nifty Next 50",sub: "NSE_INDEX · Live ticks"       },
                ],
            },
            {
                title: "Data Storage",
                items: [
                    { label: "Intraday Candles",  sub: "1m / 3m / 5m / 15m / 30m" },
                    { label: "Daily Candles",      sub: "Historical OHLCV via v3"   },
                    { label: "Instrument Sync",    sub: "50K+ NSE · BSE · MCX"     },
                    { label: "Redis Cache",        sub: "< 12ms tick latency"       },
                ],
            },
        ],
    },
    {
        key:   "indicators",
        label: "Indicators",
        icon:  <BarChart2 size={15} />,
        description: "Full TA engine — ta + TA-Lib",
        cols: [
            {
                title: "Trend & Momentum",
                items: [
                    { label: "EMA 9 / 21 / 50 / 200", sub: "Multi-period trend engine"    },
                    { label: "RSI 14",                  sub: "Momentum oscillator"          },
                    { label: "MACD + Signal + Hist",    sub: "Divergence detection"         },
                    { label: "Supertrend",              sub: "ATR-based trend direction"    },
                    { label: "ADX 14",                  sub: "Trend strength filter"        },
                ],
            },
            {
                title: "Volatility & Volume",
                items: [
                    { label: "Bollinger Bands",  sub: "Upper · Mid · Lower bands"      },
                    { label: "ATR 14",           sub: "True range volatility"          },
                    { label: "VWAP",             sub: "Daily reset · intraday"         },
                    { label: "ORB",              sub: "09:15–09:20 breakout range"     },
                    { label: "OBV · Volume SMA", sub: "Participation confirmation"     },
                ],
            },
        ],
    },
    {
        key:   "ai",
        label: "AI & Models",
        icon:  <Brain size={15} />,
        description: "ML pipeline — LightGBM + LSTM",
        cols: [
            {
                title: "Signal Models",
                items: [
                    { label: "Edge Gate",          sub: "LightGBM · AUC-based filter"  },
                    { label: "Context Expectancy", sub: "Realized-R regression model"  },
                    { label: "Edge Decay",         sub: "Rolling edge velocity tracker" },
                    { label: "LSTM Predictor",     sub: "Sequence model · 200 candles" },
                ],
            },
            {
                title: "Strategy Lab",
                items: [
                    { label: "Market Context",    sub: "15 phase labels · state machine"  },
                    { label: "Rule Evaluations",  sub: "ORB · EMA · VWAP · ATR triggers" },
                    { label: "Strategy Outcomes", sub: "TP / SL / time-exit simulation"   },
                    { label: "Paper Trading",     sub: "Capital simulation · equity curve" },
                ],
            },
        ],
    },
    {
        key:   "platform",
        label: "Platform",
        icon:  <LayoutDashboard size={15} />,
        description: "Trading console & tools",
        cols: [
            {
                title: "Core Pages",
                items: [
                    { label: "Dashboard",        sub: "Index summary · live signals"    },
                    { label: "Watchlist",        sub: "Symbol tracking · alerts"        },
                    { label: "Portfolio",        sub: "Holdings · P&L overview"         },
                    { label: "Options Trading",  sub: "Options chain · strategy builder"},
                ],
            },
            {
                title: "Infrastructure",
                items: [
                    { label: "Upstox OAuth",    sub: "Token refresh · 24h session"      },
                    { label: "PostgreSQL",       sub: "Candles · indicators · outcomes" },
                    { label: "Redis Streams",    sub: "Live ticks · candle engine"       },
                    { label: "Flask API",        sub: "20+ REST endpoints"               },
                ],
            },
        ],
    },
];

// ── Single mega menu panel ───────────────────────────────────────
function MegaPanel({ section, onClose }) {
    return (
        <div style={{
            position:   "absolute",
            top:        "calc(100% + 8px)",
            left:       "50%",
            transform:  "translateX(-50%)",
            width:      520,
            background: "var(--bg-secondary)",
            border:     "1px solid var(--border-color)",
            borderRadius: 14,
            boxShadow:  "0 20px 60px rgba(0,0,0,0.35)",
            zIndex:     1000,
            overflow:   "hidden",
            animation:  "dropIn 0.18s ease",
        }}>
            {/* Top accent */}
            <div style={{
                height: 2,
                background: "linear-gradient(90deg, var(--accent-blue), var(--accent-up))",
            }} />

            {/* Section header */}
            <div style={{
                padding:        "14px 20px 12px",
                borderBottom:   "1px solid var(--border-subtle)",
                display:        "flex",
                alignItems:     "center",
                gap:            10,
            }}>
                <span style={{ color: "var(--accent-blue)" }}>{section.icon}</span>
                <div>
                    <div style={{
                        fontSize: "0.85rem", fontWeight: 700,
                        fontFamily: "var(--font-display)",
                        color: "var(--text-primary)", letterSpacing: "-0.01em",
                    }}>
                        {section.label}
                    </div>
                    <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        {section.description}
                    </div>
                </div>
            </div>

            {/* Columns */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 0,
                padding: "16px 20px 18px",
            }}>
                {section.cols.map((col, ci) => (
                    <div key={ci} style={{
                        paddingRight: ci === 0 ? 16 : 0,
                        paddingLeft:  ci === 1 ? 16 : 0,
                        borderLeft:   ci === 1 ? "1px solid var(--border-subtle)" : "none",
                    }}>
                        <div style={{
                            fontSize: "0.65rem", fontWeight: 700,
                            letterSpacing: "0.07em", textTransform: "uppercase",
                            color: "var(--text-muted)", marginBottom: 10,
                        }}>
                            {col.title}
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                            {col.items.map((item, ii) => (
                                <div
                                    key={ii}
                                    style={{
                                        padding:      "7px 10px",
                                        borderRadius: 7,
                                        cursor:       "pointer",
                                        transition:   "background 0.12s ease",
                                    }}
                                    onMouseEnter={e => e.currentTarget.style.background = "var(--bg-tertiary)"}
                                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                                >
                                    <div style={{
                                        fontSize:   "0.8rem",
                                        fontWeight: 600,
                                        color:      "var(--text-primary)",
                                        fontFamily: "var(--font-body)",
                                    }}>
                                        {item.label}
                                    </div>
                                    <div style={{
                                        fontSize:   "0.7rem",
                                        color:      "var(--text-muted)",
                                        marginTop:  2,
                                        fontFamily: "var(--font-mono)",
                                    }}>
                                        {item.sub}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Navbar ───────────────────────────────────────────────────────
export default function Navbar() {
    const { theme, toggleTheme } = useTheme();
    const [openKey, setOpenKey]  = useState(null);
    const navRef                 = useRef(null);

    // Close on outside click
    useEffect(() => {
        function handler(e) {
            if (navRef.current && !navRef.current.contains(e.target)) {
                setOpenKey(null);
            }
        }
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    return (
        <nav
            ref={navRef}
            style={{
                height:         "var(--navbar-height)",
                background:     "var(--bg-secondary)",
                borderBottom:   "1px solid var(--border-color)",
                display:        "flex",
                alignItems:     "center",
                justifyContent: "space-between",
                padding:        "0 32px",
                position:       "relative",
                zIndex:         100,
            }}
        >
            {/* ── Logo ─────────────────────────────────── */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                <div style={{
                    width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                    background: "linear-gradient(135deg, var(--accent-blue), var(--accent-up))",
                    display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                    <TrendingUp size={16} color="#fff" />
                </div>
                <div>
                    <div style={{
                        fontFamily: "var(--font-display)",
                        fontWeight: 700, fontSize: "0.95rem",
                        color: "var(--text-primary)", letterSpacing: "-0.02em",
                        lineHeight: 1.1,
                    }}>
                        Candlesticks
                    </div>
                    <div style={{ fontSize: "0.6rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        Trading Console
                    </div>
                </div>
            </div>

            {/* ── Nav items ────────────────────────────── */}
            <div style={{ display: "flex", alignItems: "center", gap: 2, position: "relative" }}>
                {MENU_SECTIONS.map((section) => {
                    const isOpen = openKey === section.key;
                    return (
                        <div key={section.key} style={{ position: "relative" }}>
                            <button
                                onClick={() => setOpenKey(isOpen ? null : section.key)}
                                style={{
                                    display:     "flex",
                                    alignItems:  "center",
                                    gap:         6,
                                    padding:     "7px 12px",
                                    borderRadius: 7,
                                    border:      "none",
                                    background:  isOpen ? "var(--bg-tertiary)" : "transparent",
                                    color:       isOpen ? "var(--accent-blue)" : "var(--text-secondary)",
                                    fontFamily:  "var(--font-body)",
                                    fontSize:    "0.85rem",
                                    fontWeight:  isOpen ? 600 : 500,
                                    cursor:      "pointer",
                                    transition:  "all 0.15s ease",
                                }}
                                onMouseEnter={e => {
                                    if (!isOpen) e.currentTarget.style.background = "var(--bg-tertiary)";
                                }}
                                onMouseLeave={e => {
                                    if (!isOpen) e.currentTarget.style.background = "transparent";
                                }}
                            >
                                <span style={{ color: isOpen ? "var(--accent-blue)" : "var(--text-muted)" }}>
                                    {section.icon}
                                </span>
                                {section.label}
                                <ChevronDown
                                    size={13}
                                    style={{
                                        color:     "var(--text-muted)",
                                        transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
                                        transition:"transform 0.2s ease",
                                    }}
                                />
                            </button>

                            {isOpen && (
                                <MegaPanel
                                    section={section}
                                    onClose={() => setOpenKey(null)}
                                />
                            )}
                        </div>
                    );
                })}
            </div>

            {/* ── Right side ───────────────────────────── */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>

                {/* Live status pill */}
                <div style={{
                    display:     "flex", alignItems: "center", gap: 6,
                    padding:     "5px 11px", borderRadius: 999,
                    border:      "1px solid var(--border-color)",
                    background:  "var(--bg-tertiary)",
                }}>
                    <Wifi size={11} color="var(--accent-up)" />
                    <span style={{
                        fontSize: "0.68rem", fontWeight: 600,
                        color: "var(--accent-up)",
                        fontFamily: "var(--font-mono)",
                    }}>
                        LIVE
                    </span>
                </div>

                {/* Theme toggle */}
                <button
                    onClick={toggleTheme}
                    title="Toggle theme"
                    style={{
                        width: 34, height: 34, borderRadius: 7,
                        border:     "1px solid var(--border-color)",
                        background: "transparent",
                        color:      "var(--text-secondary)",
                        display:    "flex", alignItems: "center", justifyContent: "center",
                        cursor:     "pointer", transition: "all 0.15s ease",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "var(--bg-tertiary)"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                    {theme === "light" ? <Moon size={15} /> : <Sun size={15} />}
                </button>

                {/* CTA */}
                <a
                    href="/login"
                    style={{
                        display:     "flex", alignItems: "center", gap: 6,
                        padding:     "8px 16px", borderRadius: 7,
                        background:  "var(--accent-blue)",
                        color:       "#fff",
                        fontFamily:  "var(--font-body)",
                        fontSize:    "0.85rem", fontWeight: 600,
                        textDecoration: "none",
                        boxShadow:   "var(--shadow-glow-blue)",
                        transition:  "all 0.15s ease",
                    }}
                    onMouseEnter={e => {
                        e.currentTarget.style.background  = "var(--accent-blue-hover)";
                        e.currentTarget.style.boxShadow   = "0 0 24px var(--glow)";
                    }}
                    onMouseLeave={e => {
                        e.currentTarget.style.background  = "var(--accent-blue)";
                        e.currentTarget.style.boxShadow   = "var(--shadow-glow-blue)";
                    }}
                >
                    Open Console
                    <ArrowRight size={14} />
                </a>
            </div>

            {/* Drop-in animation */}
            <style>{`
                @keyframes dropIn {
                    from { opacity: 0; transform: translateX(-50%) translateY(-6px); }
                    to   { opacity: 1; transform: translateX(-50%) translateY(0);    }
                }
            `}</style>
        </nav>
    );
}
