import React, { useState, useEffect } from "react";

const LOADING_TIPS = [
    "Loading live market orderbook & real-time tick streaming...",
    "Synchronizing NSE & BSE tick feeds...",
    "Computing technical indicators & candlestick patterns...",
    "Analyzing market breadth, India VIX, and sector flows...",
    "Aligning risk management & position sizing parameters...",
];

export default function CreativePageLoader({ text, subtitle }) {
    const [tipIndex, setTipIndex] = useState(0);

    useEffect(() => {
        const timer = setInterval(() => {
            setTipIndex((prev) => (prev + 1) % LOADING_TIPS.length);
        }, 2200);
        return () => clearInterval(timer);
    }, []);

    return (
        <div style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "360px",
            padding: "40px 20px",
            width: "100%",
            boxSizing: "border-box",
        }}>
            {/* Animated Candlestick Chart Simulation */}
            <div style={{
                position: "relative",
                width: "200px",
                height: "90px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px",
                borderRadius: 14,
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                boxShadow: "0 8px 30px rgba(0,0,0,0.15)",
                overflow: "hidden",
            }}>
                {/* Horizontal Grid Lines */}
                <div style={{ position: "absolute", top: "25%", left: 0, right: 0, height: 1, background: "var(--border-subtle)", opacity: 0.5 }} />
                <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: 1, background: "var(--border-subtle)", opacity: 0.5 }} />
                <div style={{ position: "absolute", top: "75%", left: 0, right: 0, height: 1, background: "var(--border-subtle)", opacity: 0.5 }} />

                {/* Laser Scanning Line */}
                <div style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    width: "2px",
                    background: "linear-gradient(180deg, transparent, var(--accent-blue), transparent)",
                    boxShadow: "0 0 10px var(--accent-blue)",
                    animation: "laserScan 2s ease-in-out infinite alternate",
                }} />

                {/* Candlestick 1 (Green) */}
                <div className="candle" style={{ animationDelay: "0s", height: "45px" }}>
                    <div className="wick" style={{ height: "65px", background: "var(--accent-up)" }} />
                    <div className="body" style={{ height: "30px", background: "var(--accent-up)", boxShadow: "0 0 8px rgba(0,230,118,0.4)" }} />
                </div>

                {/* Candlestick 2 (Red) */}
                <div className="candle" style={{ animationDelay: "0.25s", height: "35px" }}>
                    <div className="wick" style={{ height: "55px", background: "var(--accent-down)" }} />
                    <div className="body" style={{ height: "22px", background: "var(--accent-down)", boxShadow: "0 0 8px rgba(255,82,82,0.4)" }} />
                </div>

                {/* Candlestick 3 (Green breakout) */}
                <div className="candle" style={{ animationDelay: "0.5s", height: "60px" }}>
                    <div className="wick" style={{ height: "75px", background: "var(--accent-up)" }} />
                    <div className="body" style={{ height: "42px", background: "var(--accent-up)", boxShadow: "0 0 12px rgba(0,230,118,0.5)" }} />
                </div>

                {/* Candlestick 4 (Green momentum) */}
                <div className="candle" style={{ animationDelay: "0.75s", height: "50px" }}>
                    <div className="wick" style={{ height: "70px", background: "var(--accent-up)" }} />
                    <div className="body" style={{ height: "36px", background: "var(--accent-up)", boxShadow: "0 0 8px rgba(0,230,118,0.4)" }} />
                </div>

                {/* Candlestick 5 (Doji / Consolidate) */}
                <div className="candle" style={{ animationDelay: "1s", height: "30px" }}>
                    <div className="wick" style={{ height: "60px", background: "var(--accent-blue)" }} />
                    <div className="body" style={{ height: "10px", background: "var(--accent-blue)", boxShadow: "0 0 8px rgba(59,130,246,0.4)" }} />
                </div>
            </div>

            {/* Loading text & dynamic subtext */}
            <div style={{ marginTop: 20, textAlign: "center" }}>
                <div style={{
                    fontSize: "0.95rem",
                    fontWeight: 700,
                    fontFamily: "var(--font-display)",
                    color: "var(--text-primary)",
                    letterSpacing: "-0.01em",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 8,
                }}>
                    <span style={{ animation: "spin 1.5s linear infinite", display: "inline-block" }}>⚡</span>
                    <span>{text || "Loading Market Workspace"}</span>
                </div>

                <div style={{
                    fontSize: "0.76rem",
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-mono)",
                    marginTop: 6,
                    minHeight: "20px",
                    transition: "all 0.3s ease",
                }}>
                    {subtitle || LOADING_TIPS[tipIndex]}
                </div>
            </div>

            <style>{`
                .candle {
                    position: relative;
                    width: 14px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    animation: candleBounce 1.6s ease-in-out infinite;
                }
                .wick {
                    position: absolute;
                    width: 2px;
                    border-radius: 1px;
                }
                .body {
                    position: relative;
                    width: 100%;
                    border-radius: 3px;
                    z-index: 2;
                }
                @keyframes candleBounce {
                    0%, 100% { transform: translateY(0) scaleY(1); }
                    50% { transform: translateY(-6px) scaleY(1.08); }
                }
                @keyframes laserScan {
                    0% { left: 5%; }
                    100% { left: 90%; }
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
}
