import React from "react";
import { Loader2 } from "lucide-react";
import { Card, PrimaryButton } from "./ui";

export default function OfflineOutcomesCard({
    symbol,
    outcomeLoading,
    onComputeOutcomes,
    outcomeResult,
}) {
    return (
        <Card>
            <div style={{ padding: 18 }}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div>
                        <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                            Offline
                        </div>
                        <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                            Success Outcome Evaluation
                        </div>
                        <div style={{ marginTop: 8, fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                            Evaluate how rule signals would have resolved using phase-locked future candles.
                            <div style={{ fontStyle: "italic", marginTop: 4, color: "var(--text-muted)" }}>
                                Offline only — lookahead is fixed by market phase.
                            </div>
                        </div>
                    </div>

                    <PrimaryButton
                        onClick={onComputeOutcomes}
                        disabled={outcomeLoading || !symbol}
                        icon={outcomeLoading ? <Loader2 className="animate-spin w-4 h-4" /> : null}
                    >
                        {outcomeLoading ? "Computing…" : "Compute outcomes"}
                    </PrimaryButton>
                </div>

                {outcomeResult && (
                    <div style={{
                        marginTop: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: 12,
                        padding: 14,
                        fontSize: "0.8rem",
                    }}>
                        {outcomeResult.error ? (
                            <div style={{ color: "var(--accent-down)", fontWeight: 900 }}>
                                ❌ {outcomeResult.error}
                            </div>
                        ) : (
                            <>
                                {/* Header */}
                                <div style={{
                                    fontWeight: 900,
                                    fontSize: "0.85rem",
                                    marginBottom: 10
                                }}>
                                    ✅ Strategy Outcomes Generated
                                </div>

                                {/* Metrics grid */}
                                <div style={{
                                    display: "grid",
                                    gridTemplateColumns: "1fr 1fr",
                                    gap: 8
                                }}>
                                    <div style={{ color: "var(--text-muted)" }}>Rows Processed</div>
                                    <div><b>{outcomeResult.rows_written}</b></div>

                                    {/* Optional fields (if backend updated later) */}
                                    {outcomeResult.total_trades !== undefined && (
                                        <>
                                            <div style={{ color: "var(--text-muted)" }}>Total Trades</div>
                                            <div><b>{outcomeResult.total_trades}</b></div>
                                        </>
                                    )}

                                    {outcomeResult.win_rate !== undefined && (
                                        <>
                                            <div style={{ color: "var(--text-muted)" }}>Win Rate</div>
                                            <div><b>{outcomeResult.win_rate}%</b></div>
                                        </>
                                    )}

                                    {outcomeResult.avg_r !== undefined && (
                                        <>
                                            <div style={{ color: "var(--text-muted)" }}>Avg R</div>
                                            <div><b>{outcomeResult.avg_r}</b></div>
                                        </>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>
        </Card>
    );
}

