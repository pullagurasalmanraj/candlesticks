import React, { memo } from "react";
import StockLogo from "./StockLogo";

const HeatmapTile = memo(function HeatmapTile({
    item,
    priceData,
    isSelected,
    isRunning,
    onSelect,
    onOpenTools,
}) {
    const sym = (item?.symbol || "").toUpperCase().trim();
    const ltp = priceData?.ltp;
    const change = typeof priceData?.change === "number" ? priceData.change : 0;
    const pct = typeof priceData?.percent === "number" ? priceData.percent : 0;
    const hasPrice = typeof ltp === "number";
    const isUp = hasPrice && change >= 0;

    // Calculate tile background gradient based on performance percentage
    let bgStyle = "var(--bg-secondary)";
    let borderColor = "var(--border-color)";
    let shadowGlow = "none";

    if (hasPrice && isRunning) {
        if (pct >= 2.0) {
            bgStyle = "linear-gradient(135deg, rgba(0, 230, 118, 0.25), rgba(0, 200, 83, 0.12))";
            borderColor = "rgba(0, 230, 118, 0.6)";
            shadowGlow = "0 0 16px rgba(0, 230, 118, 0.25)";
        } else if (pct > 0) {
            bgStyle = "linear-gradient(135deg, rgba(0, 230, 118, 0.15), rgba(0, 230, 118, 0.05))";
            borderColor = "rgba(0, 230, 118, 0.35)";
        } else if (pct <= -2.0) {
            bgStyle = "linear-gradient(135deg, rgba(255, 82, 82, 0.25), rgba(213, 0, 0, 0.12))";
            borderColor = "rgba(255, 82, 82, 0.6)";
            shadowGlow = "0 0 16px rgba(255, 82, 82, 0.25)";
        } else if (pct < 0) {
            bgStyle = "linear-gradient(135deg, rgba(255, 82, 82, 0.15), rgba(255, 82, 82, 0.05))";
            borderColor = "rgba(255, 82, 82, 0.35)";
        }
    }

    if (isSelected) {
        borderColor = "var(--accent-blue)";
        shadowGlow = "0 0 14px rgba(59,130,246,0.3)";
    }

    return (
        <div
            onClick={onSelect}
            style={{
                borderRadius: 12,
                border: `1px solid ${borderColor}`,
                background: bgStyle,
                boxShadow: shadowGlow,
                padding: "14px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                minHeight: 110,
                cursor: "pointer",
                position: "relative",
                overflow: "hidden",
                transition: "all 0.2s ease",
            }}
            onMouseEnter={(e) => e.currentTarget.style.transform = "translateY(-2px)"}
            onMouseLeave={(e) => e.currentTarget.style.transform = "translateY(0)"}
        >
            {/* Top row: Logo + Ticker + Stream dot */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <StockLogo symbol={sym} size={28} borderRadius={6} />
                    <div>
                        <div style={{
                            fontSize: "0.9rem",
                            fontWeight: 700,
                            fontFamily: "var(--font-display)",
                            color: "var(--text-primary)",
                            lineHeight: 1.1,
                        }}>
                            {sym}
                        </div>
                        <div style={{ fontSize: "0.62rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                            {item?.exchange || "NSE"}
                        </div>
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {isRunning && (
                        <span
                            title="Live streaming"
                            style={{
                                width: 7, height: 7, borderRadius: "50%",
                                background: "var(--accent-up)",
                                boxShadow: "0 0 8px var(--accent-up)",
                                animation: "ltsPulse 1.8s infinite ease-in-out",
                            }}
                        />
                    )}
                    {onOpenTools && (
                        <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); onOpenTools(sym); }}
                            title="Open Data Tools"
                            style={{
                                border: "none", background: "transparent", color: "var(--text-muted)",
                                cursor: "pointer", fontSize: "0.75rem", padding: 2
                            }}
                        >
                            ⚡
                        </button>
                    )}
                </div>
            </div>

            {/* Bottom row: LTP + Change % */}
            <div style={{ marginTop: 12, display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
                <div>
                    <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        LTP
                    </div>
                    <div style={{
                        fontSize: "1.1rem",
                        fontWeight: 700,
                        fontFamily: "var(--font-mono)",
                        color: hasPrice ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)",
                        fontVariantNumeric: "tabular-nums",
                        lineHeight: 1.1,
                    }}>
                        {hasPrice ? `₹${ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "--"}
                    </div>
                </div>

                <div style={{
                    fontSize: "0.85rem",
                    fontWeight: 700,
                    fontFamily: "var(--font-mono)",
                    color: hasPrice ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)",
                    background: hasPrice ? (isUp ? "rgba(0,230,118,0.18)" : "rgba(255,82,82,0.18)") : "var(--bg-tertiary)",
                    border: `1px solid ${hasPrice ? (isUp ? "rgba(0,230,118,0.3)" : "rgba(255,82,82,0.3)") : "var(--border-color)"}`,
                    borderRadius: 6,
                    padding: "3px 8px",
                    fontVariantNumeric: "tabular-nums",
                }}>
                    {hasPrice ? `${isUp ? "▲ +" : "▼ "}${pct.toFixed(2)}%` : "--"}
                </div>
            </div>
        </div>
    );
});

export default function LiveHeatmap({
    items = [],
    prices = {},
    selectedSymbol,
    activeSubscriptions = {},
    normalizeKey,
    setSelectedSymbol,
    setSelectedInstrument,
    onOpenTools,
}) {
    if (!items || items.length === 0) {
        return (
            <div style={{
                minHeight: 200,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "1px dashed var(--border-subtle)",
                borderRadius: 12,
                color: "var(--text-muted)",
                fontSize: "0.85rem",
                fontFamily: "var(--font-body)",
            }}>
                No stocks added to the stream matrix yet. Search and add symbols above to view live heatmap.
            </div>
        );
    }

    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
            gap: 14,
            width: "100%",
        }}>
            {items.map((item) => {
                const sym = (item?.symbol || "").toUpperCase();
                const key = normalizeKey ? normalizeKey(item) : (item?.instrument_key || sym);
                const priceData = prices[key] || prices[sym];
                const isSelected = selectedSymbol === sym;
                const isRunning = !!activeSubscriptions[key];

                return (
                    <HeatmapTile
                        key={key || sym}
                        item={item}
                        priceData={priceData}
                        isSelected={isSelected}
                        isRunning={isRunning}
                        onSelect={() => {
                            if (setSelectedSymbol) setSelectedSymbol(sym);
                            if (setSelectedInstrument) setSelectedInstrument(item);
                        }}
                        onOpenTools={onOpenTools}
                    />
                );
            })}
        </div>
    );
}
