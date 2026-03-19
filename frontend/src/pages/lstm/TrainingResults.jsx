import React, { useMemo } from "react";
import { Card, Chip } from "./ui";

function scoreTone(value) {
    if (typeof value !== "number") return "neutral";
    if (value >= 0.6) return "good";
    if (value >= 0.55) return "warn";
    return "bad";
}

export default function TrainingResults({ trainResults }) {
    const { edgeGates, contextModels, hasError } = useMemo(() => {
        const list = Array.isArray(trainResults) ? trainResults : [];
        return {
            edgeGates: list
                .filter((r) => r?.type === "edge_gate")
                .sort((a, b) => (b?.auc ?? 0) - (a?.auc ?? 0)),
            contextModels: list.filter((r) => r?.type === "context_expectancy" || r?.type === "edge_decay"),
            hasError: list.some((r) => r?.type === "error" || r?.status === "ERROR"),
        };
    }, [trainResults]);

    if (!trainResults) return null;

    return (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, alignItems: "start" }}>
            <Card>
                <div style={{ padding: 18 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                        <div>
                            <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                                Rule intelligence
                            </div>
                            <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                                Edge Gate Models
                            </div>
                        </div>
                        {hasError ? <Chip label="error" tone="bad" /> : <Chip label={`${edgeGates.length} models`} tone="neutral" />}
                    </div>

                    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
                        {edgeGates.length === 0 ? (
                            <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                No rule-based models trained for this symbol.
                            </div>
                        ) : edgeGates.map((r) => {
                            const auc = typeof r.auc === "number" ? r.auc : null;
                            const statusLabel = auc == null ? "—" : auc >= 0.6 ? "ACTIVE" : auc >= 0.55 ? "WEAK" : "DISABLED";
                            return (
                                <div
                                    key={r.key}
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "space-between",
                                        gap: 10,
                                        padding: "11px 12px",
                                        borderRadius: 12,
                                        background: "var(--bg-tertiary)",
                                        border: "1px solid var(--border-color)",
                                    }}
                                >
                                    <div style={{ minWidth: 0 }}>
                                        <div style={{ fontSize: "0.9rem", fontWeight: 900, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                            {(r.label || "").replace(" · Edge Gate", "")}
                                        </div>
                                        <div style={{ fontSize: "0.74rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)", marginTop: 3 }}>
                                            AUC: {auc == null ? "—" : auc.toFixed(3)}
                                        </div>
                                    </div>
                                    <Chip label={statusLabel} tone={scoreTone(auc)} />
                                </div>
                            );
                        })}
                    </div>
                </div>
            </Card>

            <Card>
                <div style={{ padding: 18 }}>
                    <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                        Market context
                    </div>
                    <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                        Context & Decay Models
                    </div>

                    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
                        {contextModels.length === 0 ? (
                            <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                No market context models available.
                            </div>
                        ) : contextModels.map((r) => (
                            <div
                                key={r.key}
                                style={{
                                    padding: "11px 12px",
                                    borderRadius: 12,
                                    background: "var(--bg-tertiary)",
                                    border: "1px solid var(--border-color)",
                                }}
                            >
                                <div style={{ fontSize: "0.9rem", fontWeight: 900, color: "var(--text-primary)" }}>
                                    {r.label}
                                </div>
                                <div style={{ fontSize: "0.74rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)", marginTop: 3 }}>
                                    RMSE: {typeof r.rmse === "number" ? r.rmse.toFixed(3) : "—"}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </Card>
        </div>
    );
}

