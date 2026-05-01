import React, { memo } from "react";
import StockLogo from "./StockLogo";

const InstrumentCard = memo(function InstrumentCard({
    item,
    prices,
    selectedSymbol,
    activeSubscriptions,
    normalizeKey,
    setSelectedSymbol,
    setSelectedInstrument,
    subscribeToStock,
    setSelectedInstruments,
}) {
    const sym        = (item.symbol || "").toUpperCase().trim();
    const key        = normalizeKey(item);
    const live       = prices?.[key] || {};
    const ltp        = live.ltp;
    const change     = typeof live.change === "number" ? live.change : 0;
    const pct        = typeof live.percent === "number" ? live.percent : 0;
    const hasPrice   = typeof ltp === "number";
    const isUp       = hasPrice && change >= 0;
    const isSelected = selectedSymbol === sym;
    const isRunning  = !!activeSubscriptions[key];
    const canShowLive = isRunning && hasPrice;

    const priceColor = !canShowLive
        ? "var(--text-muted)"
        : isUp ? "var(--accent-up)" : "var(--accent-down)";

    return (
        <div
            onClick={() => { setSelectedSymbol(sym); setSelectedInstrument(item); }}
            style={{
                display:       "flex",
                alignItems:    "center",
                gap:           10,
                padding:       "9px 11px",
                borderRadius:  10,
                cursor:        "pointer",
                transition:    "all 0.15s ease",
                background:    isSelected
                    ? "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.08))"
                    : "var(--bg-secondary)",
                border:        `1px solid ${isSelected ? "var(--accent-blue)" : "var(--border-color)"}`,
                boxShadow:     isSelected
                    ? "0 0 0 1px rgba(59,130,246,0.2), var(--shadow-card)"
                    : "var(--shadow-card)",
            }}
            onMouseEnter={e => {
                if (!isSelected) {
                    e.currentTarget.style.background  = "var(--bg-tertiary)";
                    e.currentTarget.style.borderColor = "var(--accent-blue)";
                }
            }}
            onMouseLeave={e => {
                if (!isSelected) {
                    e.currentTarget.style.background  = "var(--bg-secondary)";
                    e.currentTarget.style.borderColor = "var(--border-color)";
                }
            }}
        >
            {/* ── Live dot ──────────────────────────────────── */}
            <span style={{
                width:        6,
                height:       6,
                borderRadius: "50%",
                flexShrink:   0,
                background:   isRunning ? "var(--accent-up)" : "var(--border-color)",
                boxShadow:    isRunning ? "0 0 6px var(--accent-up)" : "none",
                transition:   "all 0.3s ease",
            }} />

            {/* ── Logo ─────────────────────────────────────── */}
            <StockLogo symbol={sym} size={32} borderRadius={8} />

            {/* ── Symbol + exchange ─────────────────────────── */}
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                    fontSize:      "13px",
                    fontWeight:    700,
                    fontFamily:    "var(--font-display)",
                    color:         "var(--text-primary)",
                    letterSpacing: "-0.02em",
                    lineHeight:    1.2,
                    whiteSpace:    "nowrap",
                    overflow:      "hidden",
                    textOverflow:  "ellipsis",
                }}>
                    {sym}
                </div>
                <div style={{
                    display:     "flex",
                    alignItems:  "center",
                    gap:         5,
                    marginTop:   3,
                }}>
                    <span style={{
                        fontSize:     "10px",
                        fontWeight:   600,
                        fontFamily:   "var(--font-mono)",
                        color:        "var(--text-secondary)",
                        background:   "var(--bg-tertiary)",
                        border:       "1px solid var(--border-color)",
                        borderRadius: 4,
                        padding:      "1px 5px",
                        letterSpacing:"0.04em",
                    }}>
                        {item.exchange || item.segment || "NSE"}
                    </span>
                    {item.instrument_type && item.instrument_type !== "EQ" && (
                        <span style={{
                            fontSize:     "10px",
                            fontFamily:   "var(--font-mono)",
                            color:        "var(--text-muted)",
                            background:   "var(--bg-secondary)",
                            border:       "1px solid var(--border-subtle)",
                            borderRadius: 4,
                            padding:      "1px 5px",
                        }}>
                            {item.instrument_type}
                        </span>
                    )}
                </div>
            </div>

            {/* ── Price ─────────────────────────────────────── */}
            <div style={{ textAlign: "right", flexShrink: 0, minWidth: 102 }}>
                <div style={{
                    fontSize:      "14px",
                    fontWeight:    700,
                    fontFamily:    "var(--font-mono)",
                    color:         priceColor,
                    lineHeight:    1.2,
                    letterSpacing: "-0.01em",
                    fontVariantNumeric: "tabular-nums",
                    textRendering: "geometricPrecision",
                }}>
                    {canShowLive ? `₹${ltp.toLocaleString("en-IN")}` : "--"}
                </div>
                <div style={{
                    fontSize:   "10.5px",
                    fontFamily: "var(--font-mono)",
                    color:      canShowLive ? priceColor : "var(--text-muted)",
                    marginTop:  2,
                    opacity:    canShowLive ? 1 : 0.5,
                    fontVariantNumeric: "tabular-nums",
                    textRendering: "geometricPrecision",
                }}>
                    {canShowLive ? `${isUp ? "▲" : "▼"} ${Math.abs(change).toFixed(2)} (${Math.abs(pct).toFixed(2)}%)`
                        : "-- (--%)"}
                </div>
            </div>

            {/* ── Buttons ───────────────────────────────────── */}
            <div
                style={{ display: "flex", gap: 6, flexShrink: 0 }}
                onClick={e => e.stopPropagation()}
            >
                {/* Stream toggle */}
                <button
                    onClick={() => subscribeToStock(item)}
                    title={isRunning ? "Stop stream" : "Start stream"}
                    style={{
                        width:          26,
                        height:         26,
                        borderRadius:   7,
                        border:         "1px solid transparent",
                        background:     isRunning
                            ? "rgba(255,82,82,0.15)"
                            : "rgba(0,230,118,0.16)",
                        color:          isRunning ? "var(--accent-down)" : "var(--accent-up)",
                        cursor:         "pointer",
                        fontSize:       "0.6rem",
                        fontWeight:     700,
                        display:        "flex",
                        alignItems:     "center",
                        justifyContent: "center",
                        transition:     "all 0.15s ease",
                        flexShrink:     0,
                    }}
                    onMouseEnter={e => {
                        e.currentTarget.style.opacity   = "0.75";
                        e.currentTarget.style.transform = "scale(1.08)";
                    }}
                    onMouseLeave={e => {
                        e.currentTarget.style.opacity   = "1";
                        e.currentTarget.style.transform = "scale(1)";
                    }}
                >
                    {isRunning ? "■" : "▶"}
                </button>

                {/* Remove */}
                <button
                    onClick={async () => {
                        if (isRunning) {
                            try {
                                await subscribeToStock(item); // toggles running script off
                            } catch {
                                // proceed with local removal even if unsubscribe fails
                            }
                        }
                        setSelectedInstruments(prev =>
                            prev.filter(p =>
                                !(p.symbol === sym &&
                                  (p.exchange || p.segment) ===
                                  (item.exchange || item.segment))
                            )
                        );
                    }}
                    title="Remove"
                    style={{
                        width:          26,
                        height:         26,
                        borderRadius:   7,
                        border:         "1px solid var(--border-color)",
                        background:     "var(--bg-secondary)",
                        color:          "var(--text-muted)",
                        cursor:         "pointer",
                        fontSize:       "0.65rem",
                        display:        "flex",
                        alignItems:     "center",
                        justifyContent: "center",
                        transition:     "all 0.15s ease",
                        flexShrink:     0,
                    }}
                    onMouseEnter={e => {
                        e.currentTarget.style.background  = "rgba(255,82,82,0.12)";
                        e.currentTarget.style.borderColor = "var(--accent-down)";
                        e.currentTarget.style.color       = "var(--accent-down)";
                        e.currentTarget.style.transform   = "scale(1.08)";
                    }}
                    onMouseLeave={e => {
                        e.currentTarget.style.background  = "var(--bg-secondary)";
                        e.currentTarget.style.borderColor = "var(--border-color)";
                        e.currentTarget.style.color       = "var(--text-muted)";
                        e.currentTarget.style.transform   = "scale(1)";
                    }}
                >
                    ✕
                </button>
            </div>
        </div>
    );
});

export default InstrumentCard;

