import React from "react";
import { BarChart3, Loader2, Wand2 } from "lucide-react";
import { Card, CardHeader, Chip, FieldLabel, Input, PrimaryButton, Select, SubtleButton } from "./ui";

export default function SearchTrainCard({
    theme,
    symbol,
    modelRunId,
    search,
    searching,
    onSearchChange,
    searchResults,
    onSelectInstrument,
    timeframe,
    onTimeframeChange,
    loading,
    onTrain,
    compareLoading,
    onCompareThresholds,
}) {
    return (
        // FIX 1: Remove overflow:"hidden" — it was clipping the search dropdown
        <Card style={{ overflow: "visible" }}>
            {/* Modern fintech hero accent */}
            <div style={{
                height: 2,
                background: "linear-gradient(90deg, var(--accent-blue), var(--accent-up))",
                borderRadius: "8px 8px 0 0",
            }} />
            <CardHeader
                subtitle="AI & Models"
                title="Model Trainer"
                icon={<BarChart3 size={16} color="#fff" />}
                right={
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
                        <Chip label={`theme:${theme}`} />
                        <Chip label={symbol ? symbol : "no symbol"} tone={symbol ? "info" : "neutral"} />
                        <Chip label={modelRunId ? `run:${modelRunId}` : "run:—"} tone={modelRunId ? "good" : "neutral"} />
                        {searching ? <Chip label="searching" tone="warn" /> : null}
                    </div>
                }
            />

            <div style={{ padding: 18 }}>
                {/* FIX 2: Remove fixed 360px column — use 1fr 1fr instead so it
                    fits inside the 340px left rail without overflow */}
                <div style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                }}>
                    {/* Symbol search */}
                    <div>
                        <FieldLabel>Symbol</FieldLabel>
                        {/* FIX 3: position:relative here so dropdown is anchored
                            to this wrapper, not the card */}
                        <div style={{ position: "relative" }}>
                            <Input
                                placeholder="Search stocks…"
                                value={search}
                                onChange={(e) => onSearchChange(e.target.value)}
                            />

                            {searchResults?.length > 0 && (
                                <div style={{
                                    position: "absolute",
                                    left: 0,
                                    right: 0,
                                    top: "calc(100% + 6px)",
                                    background: "var(--bg-secondary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 12,
                                    overflow: "hidden",
                                    // FIX 4: z-index must be high enough to float
                                    // above all sibling cards in the rail
                                    zIndex: 9999,
                                    maxHeight: 260,
                                    overflowY: "auto",
                                    boxShadow: "var(--shadow-card-hover)",
                                }}>
                                    {searchResults.map((inst) => (
                                        <div
                                            key={inst.instrument_key}
                                            onClick={(e) => { e.stopPropagation(); onSelectInstrument(inst); }}
                                            style={{
                                                padding: "10px 12px",
                                                cursor: "pointer",
                                                borderBottom: "1px solid var(--border-subtle)",
                                            }}
                                            onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-tertiary)"; }}
                                            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                                        >
                                            <div style={{ fontSize: "0.9rem", fontWeight: 900, color: "var(--text-primary)" }}>
                                                {inst.symbol}
                                            </div>
                                            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 2, fontFamily: "var(--font-mono)" }}>
                                                {inst.name} · {inst.segment}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Timeframe + Actions */}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        <div>
                            <FieldLabel>Timeframe</FieldLabel>
                            <Select value={timeframe} onChange={(e) => onTimeframeChange(e.target.value)}>
                                {["1m", "3m", "5m", "15m", "30m", "1D"].map((tf) => (
                                    <option key={tf} value={tf}>{tf}</option>
                                ))}
                            </Select>
                        </div>
                        <div>
                            <FieldLabel>Actions</FieldLabel>
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                                <PrimaryButton
                                    onClick={onTrain}
                                    disabled={loading || !symbol}
                                    icon={loading ? <Loader2 className="animate-spin w-4 h-4" /> : <Wand2 className="w-4 h-4" />}
                                >
                                    Train
                                </PrimaryButton>
                                <SubtleButton
                                    onClick={onCompareThresholds}
                                    disabled={compareLoading || !modelRunId}
                                >
                                    {compareLoading ? "Comparing…" : "Compare"}
                                </SubtleButton>
                            </div>
                        </div>
                    </div>

                    {/* Quick stats — full width, 2x2 grid */}
                    <div style={{
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: 12,
                        padding: 14,
                    }}>
                        <div style={{
                            fontSize: "0.68rem",
                            color: "var(--text-secondary)",
                            fontWeight: 800,
                            letterSpacing: "0.06em",
                            textTransform: "uppercase",
                            marginBottom: 10,
                        }}>
                            Quick stats
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            {[
                                { k: "Status", v: loading ? "training" : modelRunId ? "ready" : "idle" },
                                { k: "Run",    v: modelRunId ? "yes" : "no" },
                                { k: "Symbol", v: symbol || "—" },
                                { k: "TF",     v: timeframe },
                            ].map(({ k, v }) => (
                                <div key={k} style={{
                                    padding: "8px 10px",
                                    borderRadius: 8,
                                    background: "var(--bg-secondary)",
                                    border: "1px solid var(--border-subtle)",
                                }}>
                                    <div style={{ fontSize: "0.62rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{k}</div>
                                    <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)", marginTop: 2 }}>{v}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}
