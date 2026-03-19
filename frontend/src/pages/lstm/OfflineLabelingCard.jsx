import React from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Card, FieldLabel, Input, PrimaryButton } from "./ui";

export default function OfflineLabelingCard({
    symbol,
    windowSize,
    onWindowSizeChange,
    labelLoading,
    onRunLabeling,
    labelResult,
}) {
    return (
        <Card>
            <div style={{ padding: 18 }}>
                <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                    Offline
                </div>
                <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                    Market Context Labeling
                </div>
                <div style={{ marginTop: 8, fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                    Label historical candles with market structure and regime.
                    <div style={{ fontStyle: "italic", marginTop: 4, color: "var(--text-muted)" }}>
                        Offline only — no future data leakage.
                    </div>
                </div>

                <div style={{ marginTop: 12 }}>
                    <FieldLabel>Context window size</FieldLabel>
                    <Input
                        type="number"
                        value={windowSize}
                        onChange={(e) => onWindowSizeChange(+e.target.value)}
                    />
                </div>

                <div style={{ marginTop: 12, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                    <PrimaryButton
                        onClick={onRunLabeling}
                        disabled={labelLoading || !symbol}
                        icon={labelLoading ? <Loader2 className="animate-spin w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
                    >
                        Run labeling
                    </PrimaryButton>
                </div>

                {labelResult && (
                    <div style={{
                        marginTop: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: 12,
                        padding: 12,
                    }}>
                        {labelResult.error ? (
                            <div style={{ color: "red", fontSize: "0.8rem" }}>
                                ❌ {labelResult.error}
                            </div>
                        ) : (
                            <>
                                <div style={{ fontSize: "0.85rem", fontWeight: 700 }}>
                                    ✅ {labelResult.status}
                                </div>

                                <div style={{ marginTop: 6, fontSize: "0.8rem" }}>
                                    📊 Market Rows: <b>{labelResult.market_rows}</b>
                                </div>

                                <div style={{ fontSize: "0.8rem" }}>
                                    📈 Rule Rows: <b>{labelResult.rule_rows}</b>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>
        </Card>
    );
}

