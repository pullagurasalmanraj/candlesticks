import React, { useState, useEffect } from "react";
import ChangeBadge from "./ChangeBadge";
import { INDEX_LIST } from "../context/indexes";

// Helper to generate a smooth sparkline path
const generateSparklinePath = (data, w, h) => {
    if (!data || data.length < 2) return "";
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min === 0 ? 1 : max - min;
    return data
        .map((val, idx) => {
            const x = (idx / (data.length - 1)) * w;
            const y = h - ((val - min) / range) * (h - 4) - 2; // padding 2px top/bottom
            return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
        })
        .join(" ");
};

export default function IndexStrip({ prices, indexData }) {
    // Keep rolling history of last 15 prices for each index symbol
    const [histories, setHistories] = useState({});

    useEffect(() => {
        setHistories((prev) => {
            let changed = false;
            const next = { ...prev };

            INDEX_LIST.forEach((idx) => {
                const sym = idx.symbol.toUpperCase().replace(/ /g, "");
                const live = prices?.[sym] || null;
                const fallback = indexData?.[sym] || null;
                const ltp = live?.ltp ?? fallback?.ltp;

                if (typeof ltp === "number") {
                    const history = prev[sym] || [];
                    const lastVal = history[history.length - 1];
                    if (ltp !== lastVal) {
                        next[sym] = [...history, ltp].slice(-15);
                        changed = true;
                    }
                }
            });

            return changed ? next : prev;
        });
    }, [prices, indexData]);

    return (
        <section
            style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 12,
                padding: 12,
                borderRadius: "var(--card-radius)",
                background: "linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg-primary) 100%)",
                border: "1px solid var(--border-color)",
                boxShadow: "var(--shadow-card)",
                marginBottom: 10,
            }}
        >
            {INDEX_LIST.map((idx) => {
                const sym = idx.symbol.toUpperCase().replace(/ /g, "");
                const live = prices?.[sym] || null;
                const fallback = indexData?.[sym] || null;
                const source = live || fallback;
                const ltp = source?.ltp ?? "--";
                const change = source?.change ?? 0;
                const pct = source?.percent ?? 0;
                const up = change >= 0;
                
                // Get history or seed with current price
                const history = histories[sym] || (typeof ltp === "number" ? [ltp, ltp] : []);

                return (
                    <div
                        key={idx.name}
                        style={{
                            borderRadius: 10,
                            padding: "10px 14px",
                            display: "flex",
                            flexDirection: "column",
                            gap: 6,
                            background: "var(--bg-tertiary)",
                            border: "1px solid var(--border-subtle)",
                            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02)",
                            transition: "all 0.15s cubic-bezier(0.4, 0, 0.2, 1)",
                            position: "relative",
                            cursor: "pointer",
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.borderColor = up ? "var(--accent-up)" : "var(--accent-down)";
                            e.currentTarget.style.transform = "translateY(-1.5px)";
                            e.currentTarget.style.boxShadow = up ? "var(--shadow-glow-green)" : "var(--shadow-glow-red)";
                            e.currentTarget.style.background = "var(--bg-hover)";
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.borderColor = "var(--border-subtle)";
                            e.currentTarget.style.transform = "translateY(0)";
                            e.currentTarget.style.boxShadow = "none";
                            e.currentTarget.style.background = "var(--bg-tertiary)";
                        }}
                    >
                        {/* Top Row: Name, Sparkline, LTP */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                            <span
                                style={{
                                    fontSize: "0.85rem",
                                    fontWeight: 700,
                                    color: "var(--text-primary)",
                                    fontFamily: "var(--font-display)",
                                }}
                            >
                                {idx.display}
                            </span>
                            
                            {/* SVG Sparkline (compact) */}
                            {history.length >= 2 && (
                                <svg width="54" height="18" style={{ overflow: "visible" }}>
                                    <path
                                        d={generateSparklinePath(history, 54, 18)}
                                        fill="none"
                                        stroke={up ? "var(--accent-up)" : "var(--accent-down)"}
                                        strokeWidth="1.5"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    />
                                </svg>
                            )}

                            <span
                                style={{
                                    fontSize: "0.95rem",
                                    fontWeight: 700,
                                    color: "var(--text-primary)",
                                    fontFamily: "var(--font-mono)",
                                }}
                            >
                                {typeof ltp === "number"
                                    ? ltp.toLocaleString("en-IN", {
                                          minimumFractionDigits: 2,
                                      })
                                    : ltp}
                            </span>
                        </div>

                        {/* Bottom Row: Code Name, Change Indicator */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.7rem" }}>
                            <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontWeight: 500 }}>
                                {idx.name}
                            </span>
                            
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <span
                                    style={{
                                        fontFamily: "var(--font-mono)",
                                        fontWeight: 600,
                                        color: up ? "var(--accent-up)" : "var(--accent-down)",
                                    }}
                                >
                                    {up ? "▲" : "▼"} {Math.abs(change).toFixed(2)}
                                </span>
                                <ChangeBadge pct={pct || 0} up={up} />
                            </div>
                        </div>
                    </div>
                );
            })}
        </section>
    );
}
