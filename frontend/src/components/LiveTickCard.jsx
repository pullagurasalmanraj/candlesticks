import React, { memo, useEffect, useState } from "react";
import StockLogo from "./StockLogo";

const LiveTickCard = memo(function LiveTickCard({
    item,
    priceData,
    selectedSymbol,
    activeSubscriptions,
    normalizeKey,
    setSelectedSymbol,
    setSelectedInstrument,
    subscribeToStock,
    onRemove,
    onOpenTools,
}) {
    const sym = (item?.symbol || "").toUpperCase().trim();
    const key = normalizeKey ? normalizeKey(item) : (item?.instrument_key || sym);
    const live = priceData || {};
    const ltp = live.ltp;
    const change = typeof live.change === "number" ? live.change : 0;
    const pct = typeof live.percent === "number" ? live.percent : 0;
    const hasPrice = typeof ltp === "number";
    const isUp = hasPrice && change >= 0;
    const isSelected = selectedSymbol === sym;
    const isRunning = !!(activeSubscriptions && activeSubscriptions[key]);
    const canShowLive = isRunning && hasPrice;

    // Tick flash state management
    const [flashClass, setFlashClass] = useState("");

    useEffect(() => {
        if (!live.lastTickTs || !live.flashDir) return;
        const diff = Date.now() - live.lastTickTs;
        if (diff < 1200) {
            setFlashClass(live.flashDir === "up" ? "flash-up" : "flash-down");
            const t = setTimeout(() => setFlashClass(""), 900);
            return () => clearTimeout(t);
        }
    }, [live.lastTickTs, live.flashDir, live.ltp]);

    const priceColor = !canShowLive
        ? "var(--text-muted)"
        : isUp ? "var(--accent-up)" : "var(--accent-down)";

    return (
        <div
            onClick={() => {
                if (setSelectedSymbol) setSelectedSymbol(sym);
                if (setSelectedInstrument) setSelectedInstrument(item);
            }}
            className={`live-tick-card ${flashClass}`}
            style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "12px 14px",
                borderRadius: 12,
                cursor: "pointer",
                position: "relative",
                overflow: "hidden",
                background: isSelected
                    ? "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.06))"
                    : "var(--bg-secondary)",
                border: `1px solid ${isSelected ? "var(--accent-blue)" : "var(--border-color)"}`,
                boxShadow: isSelected
                    ? "0 0 12px rgba(59,130,246,0.25), var(--shadow-card)"
                    : "var(--shadow-card)",
                transition: "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
                gap: 12,
            }}
        >
            {/* Stream indicator bar on left border */}
            <div style={{
                position: "absolute",
                left: 0, top: 0, bottom: 0,
                width: 4,
                background: isRunning ? "var(--accent-up)" : "transparent",
                boxShadow: isRunning ? "0 0 8px var(--accent-up)" : "none",
                transition: "background 0.3s ease",
            }} />

            {/* Left section: Logo + Symbol info */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                <StockLogo symbol={sym} size={34} borderRadius={8} />

                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{
                            fontSize: "0.92rem",
                            fontWeight: 700,
                            fontFamily: "var(--font-display)",
                            color: "var(--text-primary)",
                            letterSpacing: "-0.02em",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                        }}>
                            {sym}
                        </span>

                        {isRunning && (
                            <span
                                title="Streaming live ticks"
                                style={{
                                    width: 6,
                                    height: 6,
                                    borderRadius: "50%",
                                    background: "var(--accent-up)",
                                    boxShadow: "0 0 6px var(--accent-up)",
                                    animation: "ltsPulse 1.8s infinite ease-in-out",
                                    display: "inline-block",
                                    flexShrink: 0,
                                }}
                            />
                        )}
                    </div>

                    <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        marginTop: 3,
                    }}>
                        <span style={{
                            fontSize: "0.62rem",
                            fontWeight: 600,
                            fontFamily: "var(--font-mono)",
                            color: "var(--text-muted)",
                            background: "var(--bg-tertiary)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: 4,
                            padding: "1px 5px",
                        }}>
                            {item?.exchange || item?.segment || "NSE"}
                        </span>
                        {item?.instrument_type && item.instrument_type !== "EQ" && (
                            <span style={{
                                fontSize: "0.62rem",
                                fontFamily: "var(--font-mono)",
                                color: "var(--text-muted)",
                            }}>
                                {item.instrument_type}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            {/* Center/Right section: Price + Change */}
            <div style={{ textAlign: "right", flexShrink: 0, minWidth: 110 }}>
                <div style={{
                    fontSize: "1.05rem",
                    fontWeight: 700,
                    fontFamily: "var(--font-mono)",
                    color: priceColor,
                    fontVariantNumeric: "tabular-nums",
                    lineHeight: 1.2,
                    letterSpacing: "-0.02em",
                    transition: "color 0.15s ease",
                }}>
                    {canShowLive ? `₹${ltp.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : (hasPrice ? `₹${ltp.toLocaleString("en-IN")}` : "--")}
                </div>

                <div style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 3,
                    fontSize: "0.68rem",
                    fontWeight: 600,
                    fontFamily: "var(--font-mono)",
                    color: canShowLive ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)",
                    background: canShowLive ? (isUp ? "rgba(0,230,118,0.12)" : "rgba(255,82,82,0.12)") : "var(--bg-tertiary)",
                    border: `1px solid ${canShowLive ? (isUp ? "rgba(0,230,118,0.3)" : "rgba(255,82,82,0.3)") : "var(--border-subtle)"}`,
                    borderRadius: 4,
                    padding: "1px 6px",
                    marginTop: 3,
                    fontVariantNumeric: "tabular-nums",
                }}>
                    {canShowLive ? `${isUp ? "▲ +" : "▼ "}${pct.toFixed(2)}%` : "--"}
                </div>
            </div>

            {/* Far Right Action Buttons */}
            <div
                style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Data tools shortcut for this stock */}
                {onOpenTools && (
                    <button
                        type="button"
                        onClick={() => {
                            if (setSelectedSymbol) setSelectedSymbol(sym);
                            if (setSelectedInstrument) setSelectedInstrument(item);
                            onOpenTools(sym);
                        }}
                        title="Open Data Tools for this symbol"
                        style={{
                            width: 28, height: 28, borderRadius: 7,
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-tertiary)",
                            color: "var(--accent-blue)",
                            cursor: "pointer", fontSize: "0.72rem",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            transition: "all 0.15s ease",
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.borderColor = "var(--accent-blue)";
                            e.currentTarget.style.background = "rgba(59,130,246,0.15)";
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.borderColor = "var(--border-color)";
                            e.currentTarget.style.background = "var(--bg-tertiary)";
                        }}
                    >
                        ⚡
                    </button>
                )}

                {/* Stream WSS Toggle */}
                {subscribeToStock && (
                    <button
                        type="button"
                        onClick={() => subscribeToStock(item)}
                        title={isRunning ? "Pause WSS Live Ticks" : "Start WSS Live Ticks"}
                        style={{
                            width: 28, height: 28, borderRadius: 7,
                            border: isRunning ? "1px solid rgba(255,82,82,0.5)" : "1px solid rgba(0,230,118,0.4)",
                            background: isRunning ? "rgba(255,82,82,0.18)" : "rgba(0,230,118,0.15)",
                            color: isRunning ? "var(--accent-down)" : "var(--accent-up)",
                            cursor: "pointer", fontSize: "0.65rem", fontWeight: 700,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            transition: "all 0.15s ease",
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.transform = "scale(1.08)"}
                        onMouseLeave={(e) => e.currentTarget.style.transform = "scale(1)"}
                    >
                        {isRunning ? "■" : "▶"}
                    </button>
                )}

                {/* Remove */}
                {onRemove && (
                    <button
                        type="button"
                        onClick={() => onRemove(item)}
                        title="Remove stock"
                        style={{
                            width: 28, height: 28, borderRadius: 7,
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-tertiary)",
                            color: "var(--text-muted)",
                            cursor: "pointer", fontSize: "0.7rem",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            transition: "all 0.15s ease",
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.borderColor = "var(--accent-down)";
                            e.currentTarget.style.color = "var(--accent-down)";
                            e.currentTarget.style.background = "rgba(255,82,82,0.12)";
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.borderColor = "var(--border-color)";
                            e.currentTarget.style.color = "var(--text-muted)";
                            e.currentTarget.style.background = "var(--bg-tertiary)";
                        }}
                    >
                        ✕
                    </button>
                )}
            </div>

            {/* Flash CSS animation inline rules */}
            <style>{`
                .live-tick-card.flash-up {
                    animation: tickFlashUp 0.8s ease-out forwards;
                }
                .live-tick-card.flash-down {
                    animation: tickFlashDown 0.8s ease-out forwards;
                }
                @keyframes tickFlashUp {
                    0% { background: rgba(0, 230, 118, 0.28); border-color: var(--accent-up); }
                    100% { background: var(--bg-secondary); }
                }
                @keyframes tickFlashDown {
                    0% { background: rgba(255, 82, 82, 0.28); border-color: var(--accent-down); }
                    100% { background: var(--bg-secondary); }
                }
            `}</style>
        </div>
    );
});

export default LiveTickCard;
