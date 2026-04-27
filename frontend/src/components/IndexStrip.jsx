import React from "react";
import ChangeBadge from "./ChangeBadge";
import { INDEX_LIST } from "../context/indexes";

// No isLight prop: reads CSS vars from ThemeContext automatically
export default function IndexStrip({ prices, indexData }) {
    return (
        <section
            style={{
                display: "flex",
                alignItems: "stretch",
                gap: 14,
                overflowX: "auto",
                padding: "14px 16px",
                borderRadius: "var(--card-radius)",
                background:
                    "linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg-primary) 100%)",
                border: "1px solid var(--border-color)",
                boxShadow: "var(--shadow-card)",
                scrollbarWidth: "none",
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

                return (
                    <div
                        key={idx.name}
                        style={{
                            minWidth: 228,
                            flexShrink: 0,
                            borderRadius: 14,
                            padding: "14px 16px",
                            display: "flex",
                            alignItems: "flex-start",
                            justifyContent: "space-between",
                            background:
                                "linear-gradient(160deg, var(--bg-tertiary) 0%, var(--bg-secondary) 100%)",
                            border: "1px solid var(--border-color)",
                            boxShadow: "0 8px 20px rgba(15, 23, 42, 0.18)",
                            transition: "all 0.16s ease",
                            position: "relative",
                            overflow: "hidden",
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.borderColor = "var(--accent-blue)";
                            e.currentTarget.style.transform = "translateY(-1px)";
                            e.currentTarget.style.boxShadow =
                                "0 12px 26px rgba(15, 23, 42, 0.24)";
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.borderColor = "var(--border-color)";
                            e.currentTarget.style.transform = "translateY(0)";
                            e.currentTarget.style.boxShadow =
                                "0 8px 20px rgba(15, 23, 42, 0.18)";
                        }}
                    >
                        <div
                            style={{
                                position: "absolute",
                                top: 0,
                                left: 0,
                                right: 0,
                                height: 3,
                                background: up
                                    ? "linear-gradient(90deg, rgba(0,230,118,0.1), rgba(0,230,118,0.9), rgba(0,230,118,0.1))"
                                    : "linear-gradient(90deg, rgba(255,82,82,0.1), rgba(255,82,82,0.9), rgba(255,82,82,0.1))",
                                opacity: 0.85,
                            }}
                        />

                        <div>
                            <div
                                style={{
                                    fontSize: "1rem",
                                    fontWeight: 700,
                                    color: "var(--text-primary)",
                                    fontFamily: "var(--font-display)",
                                    letterSpacing: "-0.01em",
                                }}
                            >
                                {idx.display}
                            </div>
                            <div
                                style={{
                                    fontSize: "0.76rem",
                                    color: "var(--text-muted)",
                                    fontFamily: "var(--font-mono)",
                                    marginTop: 4,
                                    letterSpacing: "0.03em",
                                }}
                            >
                                {idx.name}
                            </div>
                        </div>

                        <div style={{ textAlign: "right", paddingTop: 2 }}>
                            <div
                                style={{
                                    fontSize: "1.16rem",
                                    fontWeight: 700,
                                    color: "var(--text-primary)",
                                    fontFamily: "var(--font-mono)",
                                    letterSpacing: "-0.02em",
                                    lineHeight: 1.05,
                                }}
                            >
                                {typeof ltp === "number"
                                    ? ltp.toLocaleString("en-IN", {
                                          minimumFractionDigits: 2,
                                      })
                                    : ltp}
                            </div>
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "flex-end",
                                    gap: 6,
                                    marginTop: 7,
                                }}
                            >
                                <span
                                    style={{
                                        fontSize: "0.78rem",
                                        fontWeight: 600,
                                        fontFamily: "var(--font-mono)",
                                        color: up
                                            ? "var(--accent-up)"
                                            : "var(--accent-down)",
                                        letterSpacing: "0.02em",
                                    }}
                                >
                                    {up ? "+" : "-"} {Math.abs(change).toFixed(2)}
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
