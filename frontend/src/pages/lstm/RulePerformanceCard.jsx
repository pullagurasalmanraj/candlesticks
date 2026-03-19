import React from "react";
import { Card, SubtleButton } from "./ui";

export default function RulePerformanceCard({
    symbol,
    ruleStatsLoading,
    ruleStats,
    onRefresh,
}) {
    return (
        <Card>
            <div style={{ padding: 18 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <div>
                        <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                            Diagnostics
                        </div>
                        <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                            Rule Performance (Market Context)
                        </div>
                    </div>
                    <SubtleButton onClick={onRefresh} disabled={!symbol || ruleStatsLoading}>
                        {ruleStatsLoading ? "Loading…" : "Refresh"}
                    </SubtleButton>
                </div>

                {ruleStatsLoading && (
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 10 }}>
                        Loading rule statistics…
                    </div>
                )}

                {ruleStats?.as_of && (
                    <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: 10, fontFamily: "var(--font-mono)" }}>
                        Evaluated as of: {ruleStats.as_of}
                    </div>
                )}

                {ruleStats?.rules?.map((rule) => (
                    <div
                        key={rule.name}
                        style={{
                            marginTop: 10,
                            padding: "10px 12px",
                            borderRadius: 12,
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            gap: 12,
                            background: "var(--bg-tertiary)",
                            border: "1px solid var(--border-color)",
                        }}
                    >
                        <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: "0.9rem", fontWeight: 900, color: "var(--text-primary)" }}>
                                {rule.name}
                            </div>
                            <div style={{ marginTop: 4 }}>
                                <span style={{ fontSize: "0.78rem", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
                                    Success: {(rule.success_rate * 100).toFixed(1)}% · Failure: {(rule.failure_rate * 100).toFixed(1)}%
                                </span>
                            </div>
                            <div style={{ marginTop: 4 }}>
                                <span style={{ fontSize: "0.7rem", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                                    Evaluated at: {rule.evaluated_at}
                                </span>
                            </div>
                        </div>

                        <div
                            style={{
                                padding: "6px 10px",
                                borderRadius: 999,
                                fontSize: "0.7rem",
                                fontWeight: 900,
                                fontFamily: "var(--font-mono)",
                                whiteSpace: "nowrap",
                                backgroundColor:
                                    rule.status === "WORKING"
                                        ? "rgba(0,199,111,0.15)"
                                        : rule.status === "NOT_WORKING"
                                            ? "rgba(255,77,79,0.15)"
                                            : "rgba(255,193,7,0.15)",
                                color:
                                    rule.status === "WORKING"
                                        ? "var(--accent-up)"
                                        : rule.status === "NOT_WORKING"
                                            ? "var(--accent-down)"
                                            : "var(--text-primary)",
                            }}
                        >
                            {rule.status}
                        </div>
                    </div>
                ))}

                {!ruleStatsLoading && !ruleStats && (
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: 10 }}>
                        No rule diagnostics available yet.
                    </div>
                )}
            </div>
        </Card>
    );
}

