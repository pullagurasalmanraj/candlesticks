import React from "react";
import ChangeBadge from "./ChangeBadge";
import { INDEX_LIST } from "../context/indexes";

// No isLight prop — reads CSS vars from ThemeContext automatically
export default function IndexStrip({ prices, indexData }) {
    return (
        <section style={{
            display:      "flex",
            alignItems:   "center",
            gap:          12,
            overflowX:    "auto",
            padding:      "12px 16px",
            borderRadius: "var(--card-radius)",
            background:   "var(--bg-secondary)",
            border:       "1px solid var(--border-color)",
            boxShadow:    "var(--shadow-card)",
            scrollbarWidth: "none",
        }}>
            {INDEX_LIST.map((idx) => {
                const sym    = idx.symbol.toUpperCase().replace(/ /g, "");
                const live   = prices?.[sym] || null;
                const d      = indexData?.[sym] || null;
                const source = live || d;
                const ltp    = source?.ltp    ?? "--";
                const change = source?.change ?? 0;
                const pct    = source?.percent ?? 0;
                const up     = change >= 0;

                return (
                    <div
                        key={idx.name}
                        style={{
                            minWidth:      170,
                            flexShrink:    0,
                            borderRadius:  10,
                            padding:       "10px 14px",
                            display:       "flex",
                            alignItems:    "center",
                            justifyContent:"space-between",
                            background:    "var(--bg-tertiary)",
                            border:        "1px solid var(--border-subtle)",
                            transition:    "border-color 0.15s ease",
                        }}
                        onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent-blue)"}
                        onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border-subtle)"}
                    >
                        {/* Name */}
                        <div>
                            <div style={{
                                fontSize:   "0.8rem",
                                fontWeight: 600,
                                color:      "var(--text-primary)",
                                fontFamily: "var(--font-body)",
                            }}>
                                {idx.display}
                            </div>
                            <div style={{
                                fontSize:   "0.65rem",
                                color:      "var(--text-muted)",
                                fontFamily: "var(--font-mono)",
                                marginTop:  2,
                            }}>
                                {idx.name}
                            </div>
                        </div>

                        {/* Price */}
                        <div style={{ textAlign: "right" }}>
                            <div style={{
                                fontSize:   "0.85rem",
                                fontWeight: 700,
                                color:      "var(--text-primary)",
                                fontFamily: "var(--font-mono)",
                            }}>
                                {typeof ltp === "number"
                                    ? ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })
                                    : ltp}
                            </div>
                            <div style={{
                                display:    "flex",
                                alignItems: "center",
                                justifyContent: "flex-end",
                                gap:        6,
                                marginTop:  4,
                            }}>
                                <span style={{
                                    fontSize:   "0.7rem",
                                    fontWeight: 600,
                                    fontFamily: "var(--font-mono)",
                                    color:      up ? "var(--accent-up)" : "var(--accent-down)",
                                }}>
                                    {up ? "▲" : "▼"} {change.toFixed(2)}
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
