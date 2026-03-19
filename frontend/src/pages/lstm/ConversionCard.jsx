import React from "react";
import { Card, PrimaryButton } from "./ui";

export default function ConversionCard({ symbol, convertLoading, convertMessage, onConvertTicks }) {
    return (
        <Card>
            <div style={{ padding: 18 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                    <div>
                        <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                            Data
                        </div>
                        <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                            Tick → Candle Conversion (1m)
                        </div>
                    </div>
                    <PrimaryButton onClick={onConvertTicks} disabled={convertLoading || !symbol}>
                        {convertLoading ? "Converting…" : "Convert ticks"}
                    </PrimaryButton>
                </div>

                {convertMessage && (
                    <pre style={{
                        marginTop: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: 12,
                        padding: 12,
                        color: "var(--text-secondary)",
                        fontSize: "0.78rem",
                        fontFamily: "var(--font-mono)",
                        overflowX: "auto",
                        whiteSpace: "pre-wrap",
                    }}>
                        {convertMessage}
                    </pre>
                )}
            </div>
        </Card>
    );
}

