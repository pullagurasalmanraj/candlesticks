import React from "react";
import { Loader2 } from "lucide-react";
import { Card, Chip, FieldLabel, PrimaryButton, Select } from "./ui";

export default function PaperTradingCard({
    riskPct,
    rrRatio,
    threshold,
    onThresholdChange,
    paperLoading,
    modelRunId,
    onRunPaperTrading,
    paperProgress,
    paperPercent,
    paperResult,
}) {
    return (
        <Card>
            <div style={{ padding: 18 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                    <div>
                        <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                            Paper trading
                        </div>
                        <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                            Simulation
                        </div>
                    </div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                        <Chip label={`risk:${riskPct}%`} />
                        <Chip label={`RR:${rrRatio}`} />
                    </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
                    {[
                        { label: "Risk Model", value: "Phase Adaptive" },
                        { label: "RR Model", value: "Phase Adaptive" },
                        { label: "Max Trades / Day", value: "5" },
                        { label: "Capital Stop", value: "₹7,000" },
                    ].map((item) => (
                        <div
                            key={item.label}
                            style={{
                                padding: 12,
                                borderRadius: 12,
                                background: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                            }}
                        >
                            <div style={{ color: "var(--text-secondary)", fontSize: "0.72rem", fontFamily: "var(--font-mono)" }}>
                                {item.label}
                            </div>
                            <div style={{ fontWeight: 900, fontSize: "0.9rem", color: "var(--text-primary)", marginTop: 4 }}>
                                {item.value}
                            </div>
                        </div>
                    ))}
                </div>

                <div style={{ marginTop: 12 }}>
                    <FieldLabel>ML threshold</FieldLabel>
                    <Select value={threshold} onChange={(e) => onThresholdChange(Number(e.target.value))}>
                        <option value={0.5}>0.5</option>
                        <option value={0.6}>0.6</option>
                        <option value={0.7}>0.7</option>
                    </Select>
                </div>

                <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                    <PrimaryButton
                        onClick={onRunPaperTrading}
                        disabled={paperLoading || !modelRunId}
                        icon={paperLoading ? <Loader2 className="animate-spin w-4 h-4" /> : null}
                        style={{
                            border: "1px solid rgba(0,230,118,0.35)",
                            background: paperLoading || !modelRunId ? "var(--bg-tertiary)" : "var(--accent-up)",
                            boxShadow: paperLoading || !modelRunId ? "none" : "var(--shadow-glow-green)",
                        }}
                    >
                        {paperLoading ? "Running…" : !modelRunId ? "Train model first" : "Run paper trading"}
                    </PrimaryButton>
                    {paperProgress ? <Chip label={paperProgress} /> : null}
                    {paperPercent > 0 ? <Chip label={`${paperPercent}%`} tone="info" /> : null}
                </div>

                {paperResult && (
                    <div style={{
                        marginTop: 12,
                        padding: 14,
                        borderRadius: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                    }}>
                        {paperResult.error ? (
                            <div style={{ color: "var(--accent-down)", fontWeight: 900, fontSize: "0.85rem" }}>
                                {paperResult.error}
                            </div>
                        ) : (
                            <>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                                    <div style={{ fontSize: "0.92rem", fontWeight: 900, color: "var(--text-primary)" }}>
                                        Simulation summary
                                    </div>
                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                        <Chip label={`trades:${paperResult.total_trades}`} />
                                        <Chip label={`win:${(paperResult.win_rate * 100).toFixed(1)}%`} tone="good" />
                                    </div>
                                </div>
                                <div style={{
                                    display: "grid",
                                    gridTemplateColumns: "1fr 1fr",
                                    gap: 10,
                                    marginTop: 10,
                                    fontFamily: "var(--font-mono)",
                                    fontSize: "0.78rem",
                                    color: "var(--text-secondary)",
                                }}>
                                    <div>Start: ₹10,000</div>
                                    <div>Final: ₹{paperResult.final_capital}</div>
                                    <div>Max DD: {paperResult.max_drawdown_pct}%</div>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>
        </Card>
    );
}

