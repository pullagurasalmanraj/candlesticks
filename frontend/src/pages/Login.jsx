import React, { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import CandleBackground from "../components/CandleBackground";
import Navbar from "../components/Navbar";
import { useTheme } from "../context/ThemeContext";

import {
    Alert,
    Box,
    Button,
    Collapse,
    Divider,
    IconButton,
    InputAdornment,
    LinearProgress,
    TextField,
    Typography,
} from "@mui/material";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import LoginIcon from "@mui/icons-material/Login";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

import {
    Database,
    Activity,
    Zap,
    Brain,
    Cpu,
    FlaskConical,
    LineChart,
    Shield,
    Wifi,
    ArrowRight,
    Play,
    RefreshCw,
    Lock,
    Sparkles,
    Star,
    Award
} from "lucide-react";

function GoogleLogoIcon() {
    return (
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
            <path
                fill="#4285F4"
                d="M17.64 9.2045c0-.6382-.0573-1.2518-.1636-1.8409H9v3.4818h4.8436c-.2086 1.125-.8427 2.0782-1.7973 2.7155v2.2582h2.9082c1.7018-1.5664 2.6855-3.8741 2.6855-6.6146Z"
            />
            <path
                fill="#34A853"
                d="M9 18c2.43 0 4.4673-.8064 5.9564-2.1805l-2.9082-2.2582c-.8064.54-1.8377.8591-3.0482.8591-2.3468 0-4.3341-1.5845-5.0432-3.7132H.9573v2.3327C2.4382 15.9827 5.4818 18 9 18Z"
            />
            <path
                fill="#FBBC05"
                d="M3.9568 10.7073A5.409 5.409 0 0 1 3.6745 9c0-.5927.1023-1.1673.2823-1.7073V4.96H.9573A8.996 8.996 0 0 0 0 9c0 1.4523.3477 2.8277.9573 4.04l2.9995-2.3327Z"
            />
            <path
                fill="#EA4335"
                d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.3459l2.5814-2.5814C13.4632.8918 11.4259 0 9 0 5.4818 0 2.4382 2.0173.9573 4.96l2.9995 2.3327c.7091-2.1286 2.6964-3.7132 5.0432-3.7132Z"
            />
        </svg>
    );
}

function getPasswordStrength(password) {
    if (!password) return { score: 0, label: "", color: "transparent" };

    let score = 0;
    if (password.length >= 6) score += 1;
    if (password.length >= 10) score += 1;
    if (/[A-Z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    if (/[^A-Za-z0-9]/.test(password)) score += 1;

    const map = [
        { label: "", color: "transparent" },
        { label: "Weak", color: "#ff5252" },
        { label: "Fair", color: "#ffd54f" },
        { label: "Good", color: "#4f9eff" },
        { label: "Strong", color: "#00e676" },
        { label: "Excellent", color: "#00e676" },
    ];

    return { score, ...map[score] };
}

function validate(field, value, confirmValue) {
    if (field === "username") {
        if (!value) return "Username is required";
        if (value.length < 3) return "At least 3 characters";
        if (!/^[a-zA-Z0-9_]+$/.test(value)) return "Only letters, numbers, underscores";
    }

    if (field === "password") {
        if (!value) return "Password is required";
        if (value.length < 6) {
            const remaining = 6 - value.length;
            return `${remaining} more character${remaining > 1 ? "s" : ""} needed`;
        }
    }

    if (field === "confirm") {
        if (!value) return "Please confirm your password";
        if (value !== confirmValue) return "Passwords do not match";
    }

    return "";
}

const PROJECT_POINTS = [
    "Unified console for dashboard, watchlist, portfolio, and options workflows",
    "Live feed ingestion, analytics, broker connectivity, and low-latency cache",
    "Built-in strategy lab for rule testing and model-assisted decision support",
];

const PROJECT_STATS = [
    { value: "1.2B+", label: "Ticks processed daily" },
    { value: "85M+", label: "Candles indexed" },
    { value: "20+", label: "Core API routes" },
    { value: "<12ms", label: "Cache response latency" },
];

function InteractiveBriefMockup({ onGetStarted }) {
    const [activeSubTab, setActiveSubTab] = useState("ingestion");
    const { theme } = useTheme();

    // 1. Ingestion sub-tab state
    const [ticks, setTicks] = useState([
        { sym: "RELIANCE", price: "2,460.15", change: "+0.65%", time: "0.2s ago", up: true },
        { sym: "TCS", price: "3,892.40", change: "-0.22%", time: "0.8s ago", up: false },
        { sym: "INFY", price: "1,588.10", change: "+1.12%", time: "1.4s ago", up: true },
        { sym: "HDFCBANK", price: "1,642.50", change: "+0.15%", time: "2.1s ago", up: true },
    ]);

    useEffect(() => {
        if (activeSubTab !== "ingestion") return;
        const symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "TATAMOTORS", "BHARTIARTL"];
        const interval = setInterval(() => {
            setTicks(prev => {
                const sym = symbols[Math.floor(Math.random() * symbols.length)];
                const lastTick = prev.find(t => t.sym === sym);
                const lastPrice = parseFloat(lastTick ? lastTick.price.replace(/,/g, "") : "1500");
                const changePct = (Math.random() - 0.45) * 1.5;
                const newPrice = (lastPrice * (1 + changePct / 100)).toFixed(2);
                const formattedPrice = parseFloat(newPrice).toLocaleString('en-IN', { minimumFractionDigits: 2 });
                const newTick = {
                    sym,
                    price: formattedPrice,
                    change: (changePct >= 0 ? "+" : "") + changePct.toFixed(2) + "%",
                    time: "Just now",
                    up: changePct >= 0
                };
                const updated = prev.map(t => {
                    let nextTime = "1.0s ago";
                    if (t.time === "Just now") nextTime = "0.6s ago";
                    else {
                        const sec = parseFloat(t.time);
                        if (!isNaN(sec)) nextTime = (sec + 0.6).toFixed(1) + "s ago";
                    }
                    return { ...t, time: nextTime };
                });
                return [newTick, ...updated.filter(t => t.sym !== sym).slice(0, 3)];
            });
        }, 800);
        return () => clearInterval(interval);
    }, [activeSubTab]);

    // 2. Indicators sub-tab state
    const [selectedIndicator, setSelectedIndicator] = useState("ema");

    // 3. AI Edge sub-tab state
    const [aiCutoff, setAiCutoff] = useState(0.65);
    const getAiMetrics = (cutoff) => {
        const t = (cutoff - 0.5) / 0.4; // normalized 0 to 1
        const freq = Math.round(180 - t * 174);
        const win = (51.2 + t * 27.3).toFixed(1) + "%";
        const profit = (1.15 + t * 1.3).toFixed(2);
        const acc = (53.2 + t * 27.8).toFixed(1) + "%";
        return { freq, win, profit, acc };
    };
    const aiMetrics = getAiMetrics(aiCutoff);

    // 4. Live Simulation sub-tab state
    const [simStatus, setSimStatus] = useState("idle"); // idle, loading, running, done
    const [simLog, setSimLog] = useState([]);
    const [simTrades, setSimTrades] = useState([]);
    const [simIntervalId, setSimIntervalId] = useState(null);

    const runSimulation = () => {
        if (simStatus === "running" || simStatus === "loading") return;
        setSimStatus("loading");
        setSimLog(["[SYSTEM] Initializing simulation pipeline...", "[SYSTEM] Connecting live broker mock session...", "[SYSTEM] Ingesting 200 prior historical candles..."]);
        setSimTrades([{ x: 10, y: 120 }]);

        setTimeout(() => {
            setSimStatus("running");
            const logSteps = [
                { log: "[09:16:02] BUY NSE:RELIANCE @ 2,450.10 (ORB 5m Breakout)", trade: { x: 60, y: 95 } },
                { log: "[09:28:40] SELL NSE:RELIANCE @ 2,474.60 (+1.00% Target Hit)", trade: { x: 110, y: 60 } },
                { log: "[09:45:15] BUY NSE:TCS @ 3,820.00 (EMA 20 Support Bounce)", trade: { x: 160, y: 75 } },
                { log: "[10:12:00] SELL NSE:TCS @ 3,800.90 (-0.50% Stop Loss Hit)", trade: { x: 210, y: 90 } },
                { log: "[10:30:30] BUY NSE:INFY @ 1,602.50 (VWAP Mean Reversion)", trade: { x: 260, y: 45 } },
                { log: "[11:15:00] SELL NSE:INFY @ 1,626.50 (+1.50% Target Hit)", trade: { x: 310, y: 15 } },
            ];

            let step = 0;
            const interval = setInterval(() => {
                if (step < logSteps.length) {
                    const current = logSteps[step];
                    setSimLog(prev => [...prev, current.log]);
                    setSimTrades(prev => [...prev, current.trade]);
                    step++;
                } else {
                    clearInterval(interval);
                    setSimStatus("done");
                }
            }, 1000);
            setSimIntervalId(interval);
        }, 1200);
    };

    const resetSimulation = () => {
        if (simIntervalId) clearInterval(simIntervalId);
        setSimStatus("idle");
        setSimLog([]);
        setSimTrades([]);
    };

    useEffect(() => {
        return () => {
            if (simIntervalId) clearInterval(simIntervalId);
        };
    }, [simIntervalId]);

    return (
        <div
            style={{
                width: "100%",
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: 16,
                boxShadow: theme === "dark" 
                    ? "0 20px 45px rgba(3, 8, 20, 0.45)" 
                    : "0 12px 30px rgba(15, 23, 42, 0.12)",
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
                aspectRatio: "1.35 / 1",
            }}
        >
            {/* Window Header */}
            <div style={{
                height: 38,
                background: "var(--bg-tertiary)",
                borderBottom: "1px solid var(--border-color)",
                display: "flex",
                alignItems: "center",
                padding: "0 16px",
                gap: 8,
                position: "relative",
            }}>
                {/* Dots */}
                <div style={{ display: "flex", gap: 6 }}>
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ff5f56" }} />
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ffbd2e" }} />
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#27c93f" }} />
                </div>
                {/* URL Bar */}
                <div style={{
                    position: "absolute",
                    left: "50%",
                    transform: "translateX(-50%)",
                    background: "var(--bg-primary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 6,
                    height: 22,
                    display: "flex",
                    alignItems: "center",
                    padding: "0 16px",
                    fontSize: "0.72rem",
                    color: "var(--text-secondary)",
                    fontFamily: "var(--font-mono)",
                    minWidth: 220,
                    justifyContent: "center",
                }}>
                    <Lock size={10} style={{ marginRight: 6, color: "var(--accent-up)" }} />
                    console.candlesticks.io/dashboard
                </div>
            </div>

            {/* Inner Dashboard Layout */}
            <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
                {/* Sidebar Mock */}
                <div style={{
                    width: 50,
                    background: "var(--bg-tertiary)",
                    borderRight: "1px solid var(--border-color)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    padding: "16px 0",
                    gap: 20,
                }}>
                    <Activity size={18} color="var(--accent-blue)" />
                    <LineChart size={18} color="var(--text-muted)" />
                    <Brain size={18} color="var(--text-muted)" />
                    <FlaskConical size={18} color="var(--text-muted)" />
                </div>

                {/* Main panel inside mockup */}
                <div style={{ flex: 1, padding: 18, display: "flex", flexDirection: "column", overflow: "hidden" }}>
                    {/* Mockup Sub Tab Selectors */}
                    <div style={{
                        display: "flex",
                        borderBottom: "1px solid var(--border-color)",
                        marginBottom: 14,
                        gap: 12,
                    }}>
                        {[
                            { key: "ingestion", label: "Live Ingestion", icon: <Wifi size={12} /> },
                            { key: "indicators", label: "TA Engine", icon: <LineChart size={12} /> },
                            { key: "ai", label: "AI Forecasts", icon: <Brain size={12} /> },
                            { key: "backtest", label: "Strategy Lab", icon: <FlaskConical size={12} /> },
                        ].map(tabItem => {
                            const isSelected = activeSubTab === tabItem.key;
                            return (
                                <button
                                    key={tabItem.key}
                                    onClick={() => setActiveSubTab(tabItem.key)}
                                    style={{
                                        border: "none",
                                        background: "transparent",
                                        cursor: "pointer",
                                        padding: "6px 4px 10px",
                                        fontSize: "0.78rem",
                                        fontWeight: 600,
                                        color: isSelected ? "var(--accent-blue)" : "var(--text-secondary)",
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 5,
                                        position: "relative",
                                        transition: "all 0.15s ease",
                                    }}
                                >
                                    {tabItem.icon}
                                    {tabItem.label}
                                    {isSelected && (
                                        <div style={{
                                            position: "absolute",
                                            bottom: 0,
                                            left: 0,
                                            right: 0,
                                            height: 2,
                                            background: "var(--accent-blue)",
                                            borderRadius: 99,
                                        }} />
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    {/* Content Body */}
                    <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
                        {activeSubTab === "ingestion" && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%" }}>
                                {/* Server Blinking Lights */}
                                <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                                    {[
                                        { label: "Upstox WSS Feed" },
                                        { label: "Redis Latency <12ms" },
                                        { label: "PostgreSQL Synced" },
                                    ].map((s, idx) => (
                                        <div key={idx} style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 6,
                                            fontSize: "0.7rem",
                                            fontWeight: 600,
                                            background: "var(--bg-tertiary)",
                                            border: "1px solid var(--border-color)",
                                            borderRadius: 6,
                                            padding: "4px 8px"
                                        }}>
                                            <span style={{
                                                width: 6,
                                                height: 6,
                                                borderRadius: "50%",
                                                background: "var(--accent-up)",
                                                boxShadow: "0 0 6px var(--accent-up)",
                                                animation: "pulse 1.8s infinite"
                                            }} />
                                            {s.label}
                                        </div>
                                    ))}
                                </div>

                                {/* Stream Output */}
                                <div style={{
                                    flex: 1,
                                    background: "var(--bg-primary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 8,
                                    padding: "8px 12px",
                                    fontFamily: "var(--font-mono)",
                                    fontSize: "0.76rem",
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 6,
                                    overflowY: "hidden",
                                    justifyContent: "flex-start",
                                    boxShadow: "inset 0 2px 8px rgba(0,0,0,0.15)",
                                }}>
                                    {ticks.map((tick, i) => (
                                        <div key={i} style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            alignItems: "center",
                                            opacity: i === 0 ? 1 : 1 - i * 0.22,
                                            transition: "all 0.3s ease",
                                            padding: "2px 0"
                                        }}>
                                            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                                <span style={{
                                                    color: "var(--text-muted)",
                                                    fontSize: "0.68rem"
                                                }}>[TICK]</span>
                                                <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{tick.sym}</span>
                                            </div>
                                            <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                                                <span style={{ color: "var(--text-secondary)" }}>{tick.price}</span>
                                                <span style={{
                                                    color: tick.up ? "var(--accent-up)" : "var(--accent-down)",
                                                    fontWeight: 600,
                                                    minWidth: 54,
                                                    textAlign: "right"
                                                }}>{tick.change}</span>
                                                <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>{tick.time}</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {activeSubTab === "indicators" && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 10, height: "100%" }}>
                                {/* Sub selector pills */}
                                <div style={{ display: "flex", gap: 6 }}>
                                    {[
                                        { key: "ema", label: "EMA Trend Lines" },
                                        { key: "vwap", label: "VWAP Intraday" },
                                        { key: "supertrend", label: "Supertrend Band" },
                                        { key: "rsi", label: "RSI Momentum" },
                                    ].map(ind => (
                                        <button
                                            key={ind.key}
                                            onClick={() => setSelectedIndicator(ind.key)}
                                            style={{
                                                border: "1px solid " + (selectedIndicator === ind.key ? "var(--accent-blue)" : "var(--border-color)"),
                                                background: selectedIndicator === ind.key ? "var(--accent-blue-muted)" : "var(--bg-tertiary)",
                                                color: selectedIndicator === ind.key ? "var(--accent-blue)" : "var(--text-secondary)",
                                                borderRadius: 6,
                                                padding: "4px 8px",
                                                fontSize: "0.7rem",
                                                fontWeight: 600,
                                                cursor: "pointer",
                                                transition: "all 0.15s ease",
                                            }}
                                        >
                                            {ind.label}
                                        </button>
                                    ))}
                                </div>

                                {/* Custom SVG Candlestick Chart with Indicator Lines */}
                                <div style={{
                                    flex: 1,
                                    background: "var(--bg-primary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 8,
                                    position: "relative",
                                    overflow: "hidden",
                                    padding: 10,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                }}>
                                    <svg width="100%" height="100%" viewBox="0 0 320 140" style={{ overflow: "visible" }}>
                                        {/* Grid Lines */}
                                        <line x1="0" y1="25" x2="320" y2="25" stroke="var(--border-subtle)" strokeDasharray="3 3" />
                                        <line x1="0" y1="65" x2="320" y2="65" stroke="var(--border-subtle)" strokeDasharray="3 3" />
                                        <line x1="0" y1="105" x2="320" y2="105" stroke="var(--border-subtle)" strokeDasharray="3 3" />

                                        {/* Candlesticks: x step 32, w 14 */}
                                        <line x1="20" y1="40" x2="20" y2="90" stroke="var(--accent-up)" strokeWidth="1.5" />
                                        <rect x="13" y="50" width="14" height="30" fill="var(--accent-up)" rx="1.5" />
                                        <line x1="52" y1="45" x2="52" y2="105" stroke="var(--accent-down)" strokeWidth="1.5" />
                                        <rect x="45" y="55" width="14" height="40" fill="var(--accent-down)" rx="1.5" />
                                        <line x1="84" y1="30" x2="84" y2="85" stroke="var(--accent-up)" strokeWidth="1.5" />
                                        <rect x="77" y="38" width="14" height="35" fill="var(--accent-up)" rx="1.5" />
                                        <line x1="116" y1="20" x2="116" y2="65" stroke="var(--accent-up)" strokeWidth="1.5" />
                                        <rect x="109" y="25" width="14" height="30" fill="var(--accent-up)" rx="1.5" />
                                        <line x1="148" y1="35" x2="148" y2="95" stroke="var(--accent-down)" strokeWidth="1.5" />
                                        <rect x="141" y="45" width="14" height="35" fill="var(--accent-down)" rx="1.5" />
                                        <line x1="180" y1="50" x2="180" y2="115" stroke="var(--accent-down)" strokeWidth="1.5" />
                                        <rect x="173" y="65" width="14" height="35" fill="var(--accent-down)" rx="1.5" />
                                        <line x1="212" y1="45" x2="212" y2="100" stroke="var(--accent-up)" strokeWidth="1.5" />
                                        <rect x="205" y="50" width="14" height="38" fill="var(--accent-up)" rx="1.5" />
                                        <line x1="244" y1="25" x2="244" y2="85" stroke="var(--accent-up)" strokeWidth="1.5" />
                                        <rect x="237" y="35" width="14" height="40" fill="var(--accent-up)" rx="1.5" />
                                        <line x1="276" y1="15" x2="276" y2="65" stroke="var(--accent-up)" strokeWidth="1.5" />
                                        <rect x="269" y="20" width="14" height="35" fill="var(--accent-up)" rx="1.5" />
                                        <line x1="308" y1="10" x2="308" y2="55" stroke="var(--accent-up)" strokeWidth="1.5" />
                                        <rect x="301" y="12" width="14" height="25" fill="var(--accent-up)" rx="1.5" />

                                        {/* EMA Line */}
                                        {selectedIndicator === "ema" && (
                                            <path
                                                d="M 20 70 Q 52 75 84 55 T 148 55 T 212 70 T 276 35 T 308 22"
                                                fill="none"
                                                stroke="var(--accent-blue)"
                                                strokeWidth="2.5"
                                                strokeLinecap="round"
                                                style={{ animation: "drawPath 0.6s ease-out" }}
                                            />
                                        )}

                                        {/* VWAP Line */}
                                        {selectedIndicator === "vwap" && (
                                            <path
                                                d="M 20 62 L 52 64 L 84 58 L 116 52 L 148 56 L 180 62 L 212 60 L 244 51 L 276 43 L 308 35"
                                                fill="none"
                                                stroke="var(--accent-gold)"
                                                strokeWidth="2.5"
                                                strokeDasharray="4 3"
                                                style={{ animation: "drawPath 0.6s ease-out" }}
                                            />
                                        )}

                                        {/* Supertrend */}
                                        {selectedIndicator === "supertrend" && (
                                            <g style={{ opacity: 0.85, animation: "fadeIn 0.4s ease-out" }}>
                                                <line x1="10" y1="35" x2="70" y2="35" stroke="var(--accent-down)" strokeWidth="2.5" />
                                                <polygon points="10,35 70,35 70,42 10,42" fill="var(--accent-down)" opacity="0.12" />
                                                <line x1="70" y1="88" x2="315" y2="88" stroke="var(--accent-up)" strokeWidth="2.5" />
                                                <polygon points="70,88 315,88 315,81 70,81" fill="var(--accent-up)" opacity="0.12" />
                                            </g>
                                        )}

                                        {/* RSI */}
                                        {selectedIndicator === "rsi" && (
                                            <g style={{ animation: "slideInRsi 0.4s ease-out" }}>
                                                <rect x="10" y="105" width="300" height="30" fill="var(--bg-tertiary)" stroke="var(--border-color)" rx="4" />
                                                <line x1="10" y1="112" x2="310" y2="112" stroke="var(--border-subtle)" strokeDasharray="2 2" />
                                                <line x1="10" y1="128" x2="310" y2="128" stroke="var(--border-subtle)" strokeDasharray="2 2" />
                                                <path
                                                    d="M 15 125 L 50 128 L 85 116 L 120 110 L 155 122 L 190 126 L 225 119 L 260 112 L 295 108 L 305 111"
                                                    fill="none"
                                                    stroke="#4f9eff"
                                                    strokeWidth="2"
                                                />
                                            </g>
                                        )}
                                    </svg>
                                </div>
                            </div>
                        )}

                        {activeSubTab === "ai" && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 12, height: "100%" }}>
                                <div style={{ fontSize: "0.76rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                                    Walk-Forward validation on <strong>LightGBM + LSTM Sequence models</strong>.
                                    Adjust probability cutoff threshold below to evaluate rule filters dynamically.
                                </div>

                                <div style={{
                                    background: "var(--bg-tertiary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 10,
                                    padding: "12px 14px",
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 6
                                }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                        <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                            Confidence Threshold:
                                        </span>
                                        <span style={{
                                            fontFamily: "var(--font-mono)",
                                            fontSize: "0.85rem",
                                            fontWeight: 700,
                                            color: "var(--accent-blue)",
                                            background: "var(--bg-primary)",
                                            padding: "2px 6px",
                                            borderRadius: 4,
                                            border: "1px solid var(--border-color)"
                                        }}>
                                            {aiCutoff.toFixed(2)}
                                        </span>
                                    </div>
                                    <input
                                        type="range"
                                        min="0.50"
                                        max="0.90"
                                        step="0.05"
                                        value={aiCutoff}
                                        onChange={(e) => setAiCutoff(parseFloat(e.target.value))}
                                        style={{
                                            width: "100%",
                                            cursor: "pointer",
                                            accentColor: "var(--accent-blue)",
                                            height: 6,
                                            borderRadius: 3,
                                            background: "var(--border-color)",
                                            outline: "none"
                                        }}
                                    />
                                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.64rem", color: "var(--text-muted)" }}>
                                        <span>0.50 (Frequent Trades)</span>
                                        <span>0.90 (Conservative Edge)</span>
                                    </div>
                                </div>

                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                                    {[
                                        { label: "Model Accuracy", val: aiMetrics.acc, color: "var(--accent-blue)" },
                                        { label: "Avg. Daily Signals", val: aiMetrics.freq + " trades", color: "var(--text-primary)" },
                                        { label: "Simulated Win Rate", val: aiMetrics.win, color: "var(--accent-up)" },
                                        { label: "Profit Factor", val: aiMetrics.profit + "x", color: "var(--accent-gold)" },
                                    ].map((m, idx) => (
                                        <div key={idx} style={{
                                            background: "var(--bg-primary)",
                                            border: "1px solid var(--border-color)",
                                            borderRadius: 8,
                                            padding: "8px 10px",
                                            display: "flex",
                                            flexDirection: "column",
                                            gap: 2,
                                        }}>
                                            <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>{m.label}</span>
                                            <span style={{
                                                fontSize: "0.95rem",
                                                fontWeight: 700,
                                                color: m.color,
                                                fontFamily: "var(--font-mono)"
                                            }}>{m.val}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {activeSubTab === "backtest" && (
                            <div style={{ display: "flex", gap: 12, height: "100%", overflow: "hidden" }}>
                                <div style={{
                                    flex: 1.1,
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 8,
                                    overflow: "hidden"
                                }}>
                                    <div style={{ display: "flex", gap: 6 }}>
                                        {simStatus === "idle" && (
                                            <button
                                                onClick={runSimulation}
                                                style={{
                                                    flex: 1,
                                                    height: 30,
                                                    borderRadius: 6,
                                                    border: "none",
                                                    background: "var(--accent-blue)",
                                                    color: "#fff",
                                                    fontWeight: 600,
                                                    fontSize: "0.74rem",
                                                    cursor: "pointer",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "center",
                                                    gap: 6,
                                                    boxShadow: "var(--shadow-glow-blue)",
                                                    transition: "all 0.15s ease",
                                                }}
                                                onMouseEnter={e => e.currentTarget.style.background = "var(--accent-blue-hover)"}
                                                onMouseLeave={e => e.currentTarget.style.background = "var(--accent-blue)"}
                                            >
                                                <Play size={12} fill="#fff" />
                                                Run Simulation
                                            </button>
                                        )}

                                        {(simStatus === "running" || simStatus === "loading" || simStatus === "done") && (
                                            <button
                                                onClick={resetSimulation}
                                                style={{
                                                    flex: 1,
                                                    height: 30,
                                                    borderRadius: 6,
                                                    border: "1px solid var(--border-color)",
                                                    background: "var(--bg-tertiary)",
                                                    color: "var(--text-secondary)",
                                                    fontWeight: 600,
                                                    fontSize: "0.74rem",
                                                    cursor: "pointer",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "center",
                                                    gap: 6,
                                                }}
                                            >
                                                <RefreshCw size={12} className={simStatus === "running" || simStatus === "loading" ? "animate-spin" : ""} />
                                                {simStatus === "done" ? "Reset" : "Stop"}
                                            </button>
                                        )}
                                    </div>

                                    <div style={{
                                        flex: 1,
                                        background: "var(--bg-primary)",
                                        border: "1px solid var(--border-color)",
                                        borderRadius: 8,
                                        padding: "8px 10px",
                                        fontFamily: "var(--font-mono)",
                                        fontSize: "0.68rem",
                                        color: "var(--text-secondary)",
                                        overflowY: "auto",
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: 5,
                                    }}>
                                        {simLog.length === 0 && (
                                            <div style={{
                                                height: "100%",
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "center",
                                                color: "var(--text-muted)",
                                                fontSize: "0.7rem",
                                                textAlign: "center"
                                            }}>
                                                Click button above to simulate historical backtests.
                                            </div>
                                        )}
                                        {simLog.map((log, index) => {
                                            const isSystem = log.includes("[SYSTEM]");
                                            const isSell = log.includes("SELL");
                                            const isTarget = log.includes("Target Hit");
                                            return (
                                                <div key={index} style={{
                                                    color: isSystem ? "var(--accent-gold)" : (isSell ? (isTarget ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-primary)"),
                                                    animation: "fadeIn 0.25s ease-out"
                                                }}>
                                                    {log}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>

                                <div style={{
                                    flex: 0.9,
                                    background: "var(--bg-primary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 8,
                                    padding: 10,
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 6
                                }}>
                                    <span style={{ fontSize: "0.66rem", fontWeight: 700, color: "var(--text-muted)" }}>
                                        SIMULATED EQUITY CURVE
                                    </span>
                                    <div style={{ flex: 1, position: "relative" }}>
                                        <svg width="100%" height="100%" viewBox="0 0 320 150" style={{ overflow: "visible" }}>
                                            <line x1="0" y1="120" x2="320" y2="120" stroke="var(--border-color)" strokeWidth="1" />
                                            <line x1="0" y1="75" x2="320" y2="75" stroke="var(--border-color)" strokeWidth="0.5" strokeDasharray="2 2" />

                                            {simTrades.length > 0 && (
                                                <path
                                                    d={`M ${simTrades.map(t => `${t.x} ${t.y}`).join(" L ")}`}
                                                    fill="none"
                                                    stroke="var(--accent-up)"
                                                    strokeWidth="3"
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                />
                                            )}

                                            {simTrades.map((t, idx) => (
                                                <circle key={idx} cx={t.x} cy={t.y} r="4" fill="var(--bg-primary)" stroke="var(--accent-up)" strokeWidth="2" style={{ animation: "fadeIn 0.3s ease-out" }} />
                                            ))}
                                        </svg>
                                    </div>

                                    {simStatus === "done" && (
                                        <div style={{
                                            fontSize: "0.68rem",
                                            background: "var(--accent-up-muted)",
                                            color: "var(--accent-up)",
                                            borderRadius: 4,
                                            padding: "4px 8px",
                                            fontWeight: 600,
                                            textAlign: "center",
                                            border: "1px solid var(--accent-up)",
                                            animation: "fadeIn 0.3s ease-out"
                                        }}>
                                            Done: Net profit +$2,450.00 (+2.4%)
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

function AuthCard({
    tab,
    theme,
    username,
    setUsername,
    password,
    setPassword,
    confirm,
    setConfirm,
    showPassword,
    setShowPassword,
    showConfirm,
    setShowConfirm,
    errors,
    touch,
    handleKeyDown,
    strength,
    handleLogin,
    handleSignup,
    loading,
    apiError,
    setApiError,
    loginGoogle,
    isReturningUser,
}) {
    if (!tab) return null;

    return (
        <div
            style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: 16,
                boxShadow:
                    theme === "dark"
                        ? "0 14px 36px rgba(3, 8, 20, 0.40)"
                        : "0 10px 26px rgba(15, 23, 42, 0.11)",
                overflow: "hidden",
            }}
        >
            <div
                style={{
                    height: 3,
                    background: "linear-gradient(90deg, var(--accent-blue), var(--accent-up))",
                }}
            />

            <div style={{ padding: "24px 26px 22px" }}>
                <div style={{ marginBottom: 16 }}>
                    <Typography
                        sx={{
                            fontFamily: "var(--font-display)",
                            fontSize: "1.6rem",
                            fontWeight: 700,
                            letterSpacing: "-0.02em",
                            color: "var(--text-primary)",
                            lineHeight: 1.12,
                            mb: 0.5,
                        }}
                    >
                        {tab === "login" ? "Welcome back" : "Create account"}
                    </Typography>
                    <Typography sx={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>
                        {tab === "login"
                            ? "Sign in to continue to the trading console."
                            : "Sign up to activate your console access."}
                    </Typography>
                    {isReturningUser && tab === "login" && (
                        <Typography sx={{ mt: 1, color: "var(--text-muted)", fontSize: "0.76rem" }}>
                            Returning user detected.
                        </Typography>
                    )}
                </div>

                <Collapse in={!!apiError}>
                    <Alert
                        severity="error"
                        sx={{ mb: 2, borderRadius: "var(--input-radius)", fontSize: "0.78rem" }}
                        onClose={() => setApiError("")}
                    >
                        {apiError}
                    </Alert>
                </Collapse>

                <Box display="flex" flexDirection="column" gap={1.65}>
                    <TextField
                        label="Username"
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
                        onBlur={() => touch("username")}
                        onKeyDown={handleKeyDown}
                        error={!!errors.username}
                        helperText={errors.username}
                        fullWidth
                        size="small"
                        InputProps={{
                            startAdornment: (
                                <InputAdornment position="start">
                                    <PersonOutlineIcon sx={{ fontSize: 18, color: "var(--text-muted)" }} />
                                </InputAdornment>
                            ),
                        }}
                    />

                    <Box>
                        <TextField
                            label="Password"
                            type={showPassword ? "text" : "password"}
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            onBlur={() => touch("password")}
                            onKeyDown={handleKeyDown}
                            error={!!errors.password}
                            helperText={
                                errors.password || (tab === "signup" && password
                                    ? `Strength: ${strength.label}` : "")
                            }
                            fullWidth
                            size="small"
                            InputProps={{
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <LockOutlinedIcon sx={{ fontSize: 18, color: "var(--text-muted)" }} />
                                    </InputAdornment>
                                ),
                                endAdornment: (
                                    <InputAdornment position="end">
                                        <IconButton size="small" onClick={() => setShowPassword(!showPassword)} edge="end">
                                            {showPassword
                                                ? <VisibilityOffIcon sx={{ fontSize: 18 }} />
                                                : <VisibilityIcon sx={{ fontSize: 18 }} />}
                                        </IconButton>
                                    </InputAdornment>
                                ),
                            }}
                        />
                        {tab === "signup" && password && (
                            <Box mt={0.65} px={0.25}>
                                <LinearProgress
                                    variant="determinate"
                                    value={(strength.score / 5) * 100}
                                    sx={{
                                        height: 3,
                                        borderRadius: 2,
                                        backgroundColor: "var(--bg-tertiary)",
                                        "& .MuiLinearProgress-bar": {
                                            backgroundColor: strength.color,
                                            transition: "all 0.3s ease",
                                        },
                                    }}
                                />
                            </Box>
                        )}
                    </Box>

                    {tab === "signup" && (
                        <TextField
                            label="Confirm Password"
                            type={showConfirm ? "text" : "password"}
                            value={confirm}
                            onChange={(event) => setConfirm(event.target.value)}
                            onBlur={() => touch("confirm")}
                            onKeyDown={handleKeyDown}
                            error={!!errors.confirm}
                            helperText={errors.confirm || (confirm && confirm === password ? "Passwords match" : "")}
                            FormHelperTextProps={{
                                sx: { color: confirm && confirm === password ? "var(--accent-up)" : undefined },
                            }}
                            fullWidth
                            size="small"
                            InputProps={{
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <LockOutlinedIcon sx={{ fontSize: 18, color: "var(--text-muted)" }} />
                                    </InputAdornment>
                                ),
                                endAdornment: (
                                    <InputAdornment position="end">
                                        <IconButton size="small" onClick={() => setShowConfirm(!showConfirm)} edge="end">
                                            {showConfirm
                                                ? <VisibilityOffIcon sx={{ fontSize: 18 }} />
                                                : <VisibilityIcon sx={{ fontSize: 18 }} />}
                                        </IconButton>
                                    </InputAdornment>
                                ),
                            }}
                        />
                    )}

                    <Button
                        variant="contained"
                        startIcon={tab === "login" ? <LoginIcon /> : <PersonAddIcon />}
                        onClick={tab === "login" ? handleLogin : handleSignup}
                        disabled={loading}
                        fullWidth
                        sx={{ height: 42, mt: 0.2, fontWeight: 600, fontSize: "0.88rem" }}
                    >
                        {loading
                            ? (tab === "login" ? "Signing in..." : "Creating account...")
                            : (tab === "login" ? "Sign In" : "Create Account")}
                    </Button>

                    <Divider sx={{ my: 0.2 }}>
                        <Typography variant="caption" sx={{ color: "var(--text-muted)", px: 1 }}>
                            OR CONTINUE WITH
                        </Typography>
                    </Divider>

                    <button
                        type="button"
                        onClick={loginGoogle}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: 12,
                            width: "100%",
                            height: 48,
                            background: "#ffffff",
                            border: "1px solid #dadce0",
                            borderRadius: 6,
                            color: "#3c4043",
                            fontFamily: "\"Roboto\", \"Segoe UI\", Arial, sans-serif",
                            fontSize: "0.875rem",
                            fontWeight: 500,
                            letterSpacing: "0.2px",
                            cursor: "pointer",
                            transition: "all 0.2s ease",
                        }}
                        onMouseEnter={(event) => {
                            event.currentTarget.style.borderColor = "#d2e3fc";
                            event.currentTarget.style.background = "#f8f9fa";
                        }}
                        onMouseLeave={(event) => {
                            event.currentTarget.style.borderColor = "#dadce0";
                            event.currentTarget.style.background = "#ffffff";
                        }}
                    >
                        <GoogleLogoIcon />
                        Continue with Google
                    </button>
                </Box>
            </div>
        </div>
    );
}

export default function AuthPage() {
    const { theme } = useTheme();
    const navigate = useNavigate();

    const isLoggedIn = !!localStorage.getItem("user");
    const isReturningUser = !!localStorage.getItem("hasRegistered");

    if (isLoggedIn) return <Navigate to="/brokers" replace />;

    const [tab, setTab] = useState(null);
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [touched, setTouched] = useState({});
    const [loading, setLoading] = useState(false);
    const [apiError, setApiError] = useState("");

    const strength = getPasswordStrength(password);

    const errors = {
        username: touched.username ? validate("username", username) : "",
        password: touched.password ? validate("password", password) : "",
        confirm: touched.confirm ? validate("confirm", confirm, password) : "",
    };

    const isLoginValid = !errors.username && !errors.password && username && password;
    const isSignupValid = isLoginValid && !errors.confirm && confirm;

    const touch = (field) => setTouched((prev) => ({ ...prev, [field]: true }));

    const handleTabChange = (nextTab) => {
        setTab(nextTab);
        setTouched({});
        setApiError("");
        if (nextTab !== "signup") setConfirm("");
    };

    const handleLogin = async () => {
        setTouched({ username: true, password: true });
        if (!isLoginValid) return;

        setLoading(true);
        setApiError("");
        try {
            const res = await fetch("/api/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) {
                setApiError(data.error || "Login failed");
                return;
            }
            localStorage.setItem("user", username);
            localStorage.setItem("hasRegistered", "true");
            navigate("/brokers", { replace: true });
        } catch {
            setApiError("Network error. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const handleSignup = async () => {
        setTouched({ username: true, password: true, confirm: true });
        if (!isSignupValid) return;

        setLoading(true);
        setApiError("");
        try {
            const res = await fetch("/api/signup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) {
                setApiError(data.error || "Signup failed");
                return;
            }
            localStorage.setItem("user", username);
            localStorage.setItem("hasRegistered", "true");
            navigate("/brokers", { replace: true });
        } catch {
            setApiError("Network error. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get("error") === "google_failed") {
            setApiError("Google sign-in failed. Please try again.");
            window.history.replaceState({}, "", "/login");
            setTab("login");
        }
    }, []);

    const loginGoogle = () => {
        window.location.href = "/auth/google";
    };

    const handleKeyDown = (event) => {
        if (event.key !== "Enter") return;
        if (tab === "login") {
            handleLogin();
            return;
        }
        if (tab === "signup") handleSignup();
    };

    const pageOverlay =
        theme === "dark"
            ? "radial-gradient(circle at 12% 20%, rgba(79, 158, 255, 0.14), transparent 56%), radial-gradient(circle at 86% 78%, rgba(0, 230, 118, 0.08), transparent 52%), linear-gradient(180deg, rgba(6, 11, 24, 0.05) 0%, rgba(6, 11, 24, 0.22) 100%)"
            : "radial-gradient(circle at 12% 20%, rgba(59, 130, 246, 0.10), transparent 56%), radial-gradient(circle at 86% 78%, rgba(16, 185, 129, 0.06), transparent 52%), linear-gradient(180deg, rgba(248, 250, 252, 0.05) 0%, rgba(241, 245, 249, 0.18) 100%)";

    const statsCardSurface =
        theme === "dark" ? "rgba(13, 21, 38, 0.58)" : "rgba(255, 255, 255, 0.82)";

    return (
        <div
            className="relative w-full h-screen overflow-hidden"
            style={{ background: "var(--bg-primary)", color: "var(--text-primary)" }}
        >
            <CandleBackground />

            <div
                style={{
                    position: "absolute",
                    inset: 0,
                    zIndex: 1,
                    pointerEvents: "none",
                    background: pageOverlay,
                }}
            />

            <Navbar authMode authTab={tab} onAuthTabChange={handleTabChange} />

            <div
                className={`relative z-10 grid grid-cols-1 ${tab === null ? 'lg:grid-cols-[1.1fr_1.2fr]' : 'lg:grid-cols-[1.15fr_0.85fr]'} gap-8 px-6 lg:px-14 xl:px-20 items-center`}
                style={{
                    height: "calc(100vh - var(--navbar-height))",
                    transition: "all 0.3s ease"
                }}
            >
                <div
                    className="relative z-10 flex flex-col justify-center"
                    style={{ color: "var(--text-primary)" }}
                >
                    {tab === null ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                            <div
                                style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 6,
                                    background: "var(--accent-blue-muted)",
                                    border: "1px solid var(--accent-blue)",
                                    borderRadius: 999,
                                    padding: "4px 12px",
                                    width: "fit-content",
                                }}
                            >
                                <span
                                    style={{
                                        width: 7,
                                        height: 7,
                                        borderRadius: "50%",
                                        background: "var(--accent-blue)",
                                        boxShadow: "0 0 8px var(--accent-blue)",
                                        animation: "pulse 2s infinite",
                                    }}
                                />
                                <span
                                    style={{
                                        fontSize: 11,
                                        color: "var(--accent-blue)",
                                        fontWeight: 700,
                                        letterSpacing: "0.06em",
                                    }}
                                >
                                    TRADING RESEARCH CONSOLE
                                </span>
                            </div>

                            <h1
                                style={{
                                    fontFamily: "var(--font-display)",
                                    fontSize: "clamp(2.5rem, 5.5vw, 4.0rem)",
                                    fontWeight: 700,
                                    color: "var(--text-primary)",
                                    letterSpacing: "-0.04em",
                                    lineHeight: 1.0,
                                    maxWidth: 680,
                                }}
                            >
                                Trade Right,
                                <br />
                                <span style={{ color: "var(--accent-blue)" }}>Build Pure Edge</span>
                            </h1>

                            <p
                                style={{
                                    fontSize: "1.05rem",
                                    color: "var(--text-secondary)",
                                    maxWidth: 580,
                                    lineHeight: 1.62,
                                }}
                            >
                                Unified algorithmic research console for NSE/BSE. Ingest real-time tick feeds, run NumPy-vectorized indicators, tune machine learning thresholds, and simulate paper-trading in a single environment.
                            </p>

                            <div style={{
                                display: "flex",
                                flexDirection: "column",
                                gap: 10,
                                maxWidth: 440,
                                marginTop: 10,
                            }}>
                                <div style={{
                                    display: "flex",
                                    gap: 10,
                                    width: "100%",
                                }}>
                                    <input
                                        type="text"
                                        placeholder="Enter username to start"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        style={{
                                            flex: 1,
                                            height: 48,
                                            background: "var(--bg-secondary)",
                                            border: "1px solid var(--border-color)",
                                            borderRadius: "var(--input-radius)",
                                            color: "var(--text-primary)",
                                            padding: "0 16px",
                                            fontSize: "0.95rem",
                                            fontFamily: "var(--font-body)",
                                            outline: "none",
                                            transition: "border-color 0.15s ease",
                                        }}
                                        onFocus={(e) => e.target.style.borderColor = "var(--accent-blue)"}
                                        onBlur={(e) => e.target.style.borderColor = "var(--border-color)"}
                                    />
                                    <button
                                        onClick={() => {
                                            handleTabChange("signup");
                                        }}
                                        style={{
                                            height: 48,
                                            padding: "0 22px",
                                            background: "var(--accent-blue)",
                                            color: "#ffffff",
                                            fontSize: "0.92rem",
                                            fontWeight: 600,
                                            borderRadius: "var(--button-radius)",
                                            border: "none",
                                            cursor: "pointer",
                                            boxShadow: "var(--shadow-glow-blue)",
                                            transition: "all 0.15s ease",
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 8,
                                        }}
                                        onMouseEnter={(e) => e.currentTarget.style.background = "var(--accent-blue-hover)"}
                                        onMouseLeave={(e) => e.currentTarget.style.background = "var(--accent-blue)"}
                                    >
                                        Get Started Free
                                        <ArrowRight size={16} />
                                    </button>
                                </div>
                                <span style={{
                                    fontSize: "0.78rem",
                                    color: "var(--text-muted)",
                                }}>
                                    Already have an account?{" "}
                                    <button
                                        onClick={() => handleTabChange("login")}
                                        style={{
                                            border: "none",
                                            background: "transparent",
                                            color: "var(--accent-blue)",
                                            fontWeight: 600,
                                            cursor: "pointer",
                                            padding: 0,
                                            fontSize: "inherit",
                                        }}
                                    >
                                        Sign In
                                    </button>
                                </span>
                            </div>

                            <div style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 30,
                                borderTop: "1px solid var(--border-subtle)",
                                paddingTop: 20,
                                marginTop: 15,
                                flexWrap: "wrap",
                            }}>
                                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    <span style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
                                        4.9 ★
                                    </span>
                                    <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                        Avg. Console Rating
                                    </span>
                                </div>
                                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    <span style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
                                        1.2B+
                                    </span>
                                    <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                        Ticks Processed Daily
                                    </span>
                                </div>
                                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    <span style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                                        FREE
                                    </span>
                                    <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                        Account Opening
                                    </span>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                            <div
                                style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 6,
                                    background: "var(--accent-blue-muted)",
                                    border: "1px solid var(--accent-blue)",
                                    borderRadius: 999,
                                    padding: "4px 12px",
                                    width: "fit-content",
                                }}
                            >
                                <span
                                    style={{
                                        width: 7,
                                        height: 7,
                                        borderRadius: "50%",
                                        background: "var(--accent-blue)",
                                        boxShadow: "0 0 8px var(--accent-blue)",
                                        animation: "pulse 2s infinite",
                                    }}
                                />
                                <span
                                    style={{
                                        fontSize: 11,
                                        color: "var(--accent-blue)",
                                        fontWeight: 700,
                                        letterSpacing: "0.06em",
                                    }}
                                >
                                    PROJECT OVERVIEW
                                </span>
                            </div>

                            <h1
                                style={{
                                    fontFamily: "var(--font-display)",
                                    fontSize: "clamp(2.2rem, 5vw, 3.8rem)",
                                    fontWeight: 700,
                                    color: "var(--text-primary)",
                                    letterSpacing: "-0.03em",
                                    lineHeight: 1.02,
                                    maxWidth: 600,
                                }}
                            >
                                Trade Intelligence
                                <br />
                                <span style={{ color: "var(--accent-blue)" }}>At Data Scale</span>
                            </h1>

                            <p
                                style={{
                                    fontSize: "0.95rem",
                                    color: "var(--text-secondary)",
                                    maxWidth: 580,
                                    lineHeight: 1.58,
                                }}
                            >
                                High-frequency market workflows with live ingestion, indicator analytics, strategy tooling, and broker execution from a single console.
                            </p>

                            <div
                                style={{
                                    display: "grid",
                                    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                                    gap: 12,
                                    maxWidth: 560,
                                    marginTop: 10,
                                }}
                            >
                                {PROJECT_STATS.slice(0, 2).map((item) => (
                                    <div
                                        key={item.label}
                                        style={{
                                            background: statsCardSurface,
                                            border: "1px solid var(--border-color)",
                                            borderRadius: 12,
                                            padding: "12px 14px",
                                            backdropFilter: "blur(4px)",
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontFamily: "var(--font-mono)",
                                                fontSize: "1.45rem",
                                                fontWeight: 700,
                                                color: "var(--text-primary)",
                                                lineHeight: 1.1,
                                            }}
                                        >
                                            {item.value}
                                        </div>
                                        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 3 }}>
                                            {item.label}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                <div className="relative z-10 flex items-center justify-center">
                    <div style={{ width: "100%", maxWidth: tab === null ? 620 : 430, transition: "max-width 0.3s ease" }}>
                        {tab === null ? (
                            <InteractiveBriefMockup onGetStarted={() => handleTabChange("signup")} />
                        ) : (
                            <AuthCard
                                tab={tab}
                                theme={theme}
                                username={username}
                                setUsername={setUsername}
                                password={password}
                                setPassword={setPassword}
                                confirm={confirm}
                                setConfirm={setConfirm}
                                showPassword={showPassword}
                                setShowPassword={setShowPassword}
                                showConfirm={showConfirm}
                                setShowConfirm={setShowConfirm}
                                errors={errors}
                                touch={touch}
                                handleKeyDown={handleKeyDown}
                                strength={strength}
                                handleLogin={handleLogin}
                                handleSignup={handleSignup}
                                loading={loading}
                                apiError={apiError}
                                setApiError={setApiError}
                                loginGoogle={loginGoogle}
                                isReturningUser={isReturningUser}
                            />
                        )}
                    </div>
                </div>
            </div>

            <style>{`
                @keyframes pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.65; transform: scale(1.2); }
                }
                @keyframes drawPath {
                    from { stroke-dasharray: 400; stroke-dashoffset: 400; }
                    to { stroke-dasharray: 400; stroke-dashoffset: 0; }
                }
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                @keyframes slideInRsi {
                    from { transform: translateY(12px); opacity: 0; }
                    to { transform: translateY(0); opacity: 1; }
                }
            `}</style>
        </div>
    );
}
