import React from "react";
import { Search } from "lucide-react";
import { Card, Chip, FieldLabel, Input } from "./ui";

function formatExpiry(expiry) {
    if (!expiry) return "—";
    try {
        // backend likely returns date or ISO string
        const d = new Date(expiry);
        if (Number.isNaN(d.getTime())) return String(expiry);
        return d.toLocaleDateString();
    } catch {
        return String(expiry);
    }
}

export default function OptionsContractSearchCard({
    query,
    onQueryChange,
    loading,
    results,
    selected,
    onSelect,
}) {
    return (
        <Card>
            <div style={{ padding: 18 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                    <div>
                        <div style={{ fontSize: "0.68rem", fontWeight: 900, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                            Options
                        </div>
                        <div style={{ fontSize: "0.95rem", fontWeight: 900, fontFamily: "var(--font-display)", marginTop: 4, color: "var(--text-primary)" }}>
                            Contract Search
                        </div>
                    </div>
                    {selected?.symbol ? (
                        <Chip label={selected.symbol} tone="info" />
                    ) : (
                        <Chip label={loading ? "Searching…" : `${results?.length || 0} results`} tone="neutral" />
                    )}
                </div>

                <div style={{ marginTop: 12 }}>
                    <FieldLabel>Search by contract / underlying</FieldLabel>
                    <div style={{ position: "relative" }}>
                        <Input
                            placeholder="e.g. NIFTY, BANKNIFTY, RELIANCE…"
                            value={query}
                            onChange={(e) => onQueryChange(e.target.value)}
                            style={{ paddingLeft: 36 }}
                        />
                        <div style={{
                            position: "absolute",
                            left: 10,
                            top: "50%",
                            transform: "translateY(-50%)",
                            color: "var(--text-muted)",
                            pointerEvents: "none",
                        }}>
                            <Search size={16} />
                        </div>
                    </div>
                </div>

                {results?.length > 0 && (
                    <div style={{
                        marginTop: 12,
                        maxHeight: 320,
                        overflowY: "auto",
                        borderRadius: 12,
                        background: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                    }}>
                        {results.map((c, idx) => {
                            const isSel = selected?.instrument_key && selected.instrument_key === c.instrument_key;
                            return (
                                <div
                                    key={c.instrument_key || `${c.symbol}-${idx}`}
                                    onClick={() => onSelect(c)}
                                    style={{
                                        display: "grid",
                                        gridTemplateColumns: "minmax(0, 1fr) auto",
                                        gap: 10,
                                        padding: "10px 12px",
                                        cursor: "pointer",
                                        background: isSel ? "var(--accent-blue-muted)" : "transparent",
                                        borderBottom: idx !== results.length - 1 ? "1px solid var(--border-color)" : "none",
                                    }}
                                    onMouseEnter={(e) => { if (!isSel) e.currentTarget.style.background = "var(--bg-hover)"; }}
                                    onMouseLeave={(e) => { if (!isSel) e.currentTarget.style.background = "transparent"; }}
                                >
                                    <div style={{ minWidth: 0 }}>
                                        <div style={{
                                            fontSize: "0.88rem",
                                            fontWeight: 900,
                                            color: "var(--text-primary)",
                                            whiteSpace: "nowrap",
                                            overflow: "hidden",
                                            textOverflow: "ellipsis",
                                            fontFamily: "var(--font-mono)",
                                        }}>
                                            {c.symbol}
                                        </div>
                                        <div style={{ marginTop: 4, fontSize: "0.74rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                                            {c.underlying || "—"} · {c.instrument_type || "—"} · ₹{c.strike_price ?? "—"} · {formatExpiry(c.expiry)}
                                        </div>
                                    </div>
                                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                                        <Chip label={c.instrument_type || "OPT"} tone={c.instrument_type === "CE" ? "good" : c.instrument_type === "PE" ? "bad" : "neutral"} />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {query?.trim()?.length >= 2 && (results?.length || 0) === 0 && !loading && (
                    <div style={{ marginTop: 12, fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                        No contracts found.
                    </div>
                )}
            </div>
        </Card>
    );
}

