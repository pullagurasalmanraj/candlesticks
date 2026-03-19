import React from "react";
import { Card } from "./ui";

export default function EquityCurveCard({ equityLoading, equityCurve }) {
    return (
        <Card>
            <div style={{ padding: 18 }}>
                <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                    Paper trading
                </div>
                <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                    Equity Curve
                </div>

                {equityLoading && (
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 10 }}>
                        Loading equity curve…
                    </div>
                )}

                {!equityLoading && (!equityCurve || equityCurve.length === 0) && (
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 10 }}>
                        No equity data available.
                    </div>
                )}

                {!equityLoading && equityCurve?.length > 0 && (
                    <div style={{
                        marginTop: 10,
                        maxHeight: 280,
                        overflowY: "auto",
                        borderRadius: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                    }}>
                        {equityCurve.map((p, idx) => (
                            <div
                                key={idx}
                                style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    padding: "8px 12px",
                                    fontSize: "0.78rem",
                                    borderBottom: idx !== equityCurve.length - 1 ? "1px solid var(--border-color)" : "none",
                                }}
                            >
                                <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                                    {new Date(p.time).toLocaleString()}
                                </span>
                                <span style={{
                                    fontFamily: "var(--font-mono)",
                                    fontWeight: 900,
                                    color: p.capital >= 10000 ? "var(--accent-up)" : "var(--accent-down)",
                                }}>
                                    ₹{Number(p.capital).toFixed(2)}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </Card>
    );
}

