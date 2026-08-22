import React, { useState, useEffect, useMemo } from "react";
import { useTheme } from "../context/ThemeContext";

export default function IntradayMarginCalculator({ symbol, ltp, instrument, initialMarginData }) {
    const { theme } = useTheme();
    const isDark = theme === "dark";

    const [marginInfo, setMarginInfo] = useState(initialMarginData || null);
    const [loading, setLoading] = useState(!initialMarginData);
    const [tradeCapital, setTradeCapital] = useState(5000); // Default ₹5,000
    const [customQty, setCustomQty] = useState("");

    const cleanSymbol = useMemo(() => {
        return String(symbol || "").split("|").pop().replace(/^(NSE_EQ:|NSE_EQ\||BSE_EQ:|BSE_EQ\|)/, "").replace(/[^A-Z0-9]/g, "").trim().toUpperCase();
    }, [symbol]);

    // Fetch live MIS Margin info if not provided
    useEffect(() => {
        if (initialMarginData) {
            setMarginInfo(initialMarginData);
            setLoading(false);
            return;
        }

        if (!cleanSymbol) return;

        let isMounted = true;
        setLoading(true);

        fetch(`/api/margin-info/${cleanSymbol}`)
            .then(res => res.json())
            .then(resData => {
                if (isMounted && resData?.status === "success" && resData?.data) {
                    setMarginInfo(resData.data);
                }
            })
            .catch(err => console.error("Failed to fetch margin info:", err))
            .finally(() => { if (isMounted) setLoading(false); });

        return () => { isMounted = false; };
    }, [cleanSymbol, initialMarginData]);

    const currentPrice = Number(ltp) || 0;
    const marginPct = marginInfo?.intraday_margin || 20.0;
    const leverage = marginInfo?.intraday_leverage || (100.0 / marginPct);
    const misPricePerShare = currentPrice > 0 ? (currentPrice * (marginPct / 100.0)) : 0;
    const capitalSavedPct = currentPrice > 0 ? (100.0 - marginPct) : 80.0;

    // Position sizing calculations
    const maxMisQty = (misPricePerShare > 0 && tradeCapital > 0) ? Math.floor(tradeCapital / misPricePerShare) : 0;
    const maxCncQty = (currentPrice > 0 && tradeCapital > 0) ? Math.floor(tradeCapital / currentPrice) : 0;

    const activeQty = customQty ? parseInt(customQty, 10) || 0 : maxMisQty;
    const requiredMisCapital = activeQty * misPricePerShare;
    const totalExposure = activeQty * currentPrice;

    const capitalPresets = [5000, 10000, 25000, 50000, 100000, 250000];

    return (
        <div style={{
            background: "var(--bg-tertiary)",
            border: "1px solid var(--border-color)",
            borderRadius: 14,
            padding: "18px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
            boxSizing: "border-box",
            width: "100%",
            color: "var(--text-primary)",
            fontFamily: "var(--font-sans, Inter, sans-serif)",
            boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
        }}>
            {/* Header: Title + Leverage Badge */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-color)", paddingBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{
                        width: 32, height: 32, borderRadius: 8,
                        background: "rgba(59, 130, 246, 0.15)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: "1.1rem", border: "1px solid rgba(59, 130, 246, 0.3)"
                    }}>
                        ⚡
                    </div>
                    <div>
                        <div style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", color: "var(--accent-blue)", letterSpacing: "0.05em" }}>
                            NSE MIS Intraday Margin
                        </div>
                        <div style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--text-primary)" }}>
                            {cleanSymbol || "Stock"} Margin & Leverage
                        </div>
                    </div>
                </div>

                <div style={{
                    background: "rgba(16, 185, 129, 0.12)",
                    border: "1px solid rgba(16, 185, 129, 0.3)",
                    color: "var(--accent-up)",
                    borderRadius: 6,
                    padding: "4px 10px",
                    fontSize: "0.74rem",
                    fontWeight: 800,
                    fontFamily: "var(--font-mono)",
                }}>
                    {leverage.toFixed(1)}x Leverage ({marginPct}% Margin)
                </div>
            </div>

            {/* Price Comparison Cards: CNC vs MIS */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 10,
            }}>
                {/* 1. Original Delivery / CNC Price */}
                <div style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 10,
                    padding: "12px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                }}>
                    <div style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                        📦 CNC Original Price
                    </div>
                    <div style={{ fontSize: "1.3rem", fontWeight: 900, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                        {currentPrice > 0 ? `₹${currentPrice.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "--"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>
                        100% Capital per share
                    </div>
                </div>

                {/* 2. Intraday MIS Price */}
                <div style={{
                    background: "linear-gradient(135deg, rgba(59, 130, 246, 0.08), rgba(16, 185, 129, 0.08))",
                    border: "1px solid rgba(59, 130, 246, 0.35)",
                    borderRadius: 10,
                    padding: "12px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                }}>
                    <div style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", color: "var(--accent-blue)", display: "flex", justifyContent: "space-between" }}>
                        <span>⚡ MIS Intraday Price</span>
                        <span style={{ color: "var(--accent-up)", fontWeight: 800 }}>Save {capitalSavedPct.toFixed(0)}%</span>
                    </div>
                    <div style={{ fontSize: "1.3rem", fontWeight: 900, fontFamily: "var(--font-mono)", color: "var(--accent-up)" }}>
                        {misPricePerShare > 0 ? `₹${misPricePerShare.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "--"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-secondary)" }}>
                        Only {marginPct}% margin needed
                    </div>
                </div>
            </div>

            {/* Interactive Trade Capital Input & Presets */}
            <div style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: 10,
                padding: "14px",
                display: "flex",
                flexDirection: "column",
                gap: 10,
            }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--text-primary)" }}>
                        💰 Your Intraday Trade Capital:
                    </label>
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>₹</span>
                        <input
                            type="number"
                            min="500"
                            step="500"
                            value={tradeCapital}
                            onChange={(e) => {
                                const val = Number(e.target.value);
                                setTradeCapital(val >= 0 ? val : 0);
                                setCustomQty("");
                            }}
                            style={{
                                width: 100,
                                padding: "4px 8px",
                                fontSize: "0.82rem",
                                fontWeight: 800,
                                fontFamily: "var(--font-mono)",
                                color: "var(--accent-blue)",
                                background: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                borderRadius: 6,
                                textAlign: "right",
                            }}
                        />
                    </div>
                </div>

                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {capitalPresets.map((cap) => (
                        <button
                            key={cap}
                            type="button"
                            onClick={() => { setTradeCapital(cap); setCustomQty(""); }}
                            style={{
                                background: tradeCapital === cap ? "var(--accent-blue)" : "var(--bg-tertiary)",
                                color: tradeCapital === cap ? "#fff" : "var(--text-secondary)",
                                border: `1px solid ${tradeCapital === cap ? "var(--accent-blue)" : "var(--border-color)"}`,
                                borderRadius: 6,
                                padding: "4px 8px",
                                fontSize: "0.7rem",
                                fontWeight: 700,
                                cursor: "pointer",
                                transition: "all 0.15s ease",
                            }}
                        >
                            ₹{(cap / 1000).toFixed(0)}k
                        </button>
                    ))}
                </div>
            </div>

            {/* Real-time Position Sizing Results */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 8,
                background: "var(--bg-secondary)",
                padding: "12px",
                borderRadius: 10,
                border: "1px solid var(--border-color)",
            }}>
                <div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 600 }}>
                        Max MIS Quantity
                    </div>
                    <div style={{ fontSize: "1.15rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--accent-up)" }}>
                        {maxMisQty.toLocaleString("en-IN")} <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)" }}>shares</span>
                    </div>
                    <div style={{ fontSize: "0.64rem", color: "var(--text-muted)" }}>
                        vs {maxCncQty} CNC shares
                    </div>
                </div>

                <div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 600 }}>
                        Total Exposure Value
                    </div>
                    <div style={{ fontSize: "1.15rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                        ₹{totalExposure > 0 ? (totalExposure / 100000).toFixed(2) : "0.00"} <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)" }}>Lakh</span>
                    </div>
                    <div style={{ fontSize: "0.64rem", color: "var(--accent-blue)" }}>
                        {leverage.toFixed(1)}x Buying Power
                    </div>
                </div>
            </div>

            {/* P&L Simulator Matrix */}
            <div style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                background: "var(--bg-secondary)",
                padding: "12px",
                borderRadius: 10,
                border: "1px solid var(--border-color)",
            }}>
                <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-primary)", display: "flex", justifyContent: "space-between" }}>
                    <span>🎯 Expected Intraday Return / Risk Simulator</span>
                    <span style={{ fontSize: "0.66rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        For {activeQty} Qty
                    </span>
                </div>

                <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(3, 1fr)",
                    gap: 6,
                    marginTop: 4,
                }}>
                    <div style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.25)", padding: "6px 8px", borderRadius: 6, textAlign: "center" }}>
                        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>+1.0% Target</div>
                        <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                            +₹{((totalExposure * 0.01) || 0).toFixed(0)}
                        </div>
                        <div style={{ fontSize: "0.62rem", color: "var(--accent-up)", fontWeight: 700 }}>+{(leverage * 1.0).toFixed(1)}% ROI</div>
                    </div>

                    <div style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.25)", padding: "6px 8px", borderRadius: 6, textAlign: "center" }}>
                        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>+2.0% Target</div>
                        <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                            +₹{((totalExposure * 0.02) || 0).toFixed(0)}
                        </div>
                        <div style={{ fontSize: "0.62rem", color: "var(--accent-up)", fontWeight: 700 }}>+{(leverage * 2.0).toFixed(1)}% ROI</div>
                    </div>

                    <div style={{ background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.25)", padding: "6px 8px", borderRadius: 6, textAlign: "center" }}>
                        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>-0.5% SL Risk</div>
                        <div style={{ fontSize: "0.82rem", fontWeight: 800, color: "var(--accent-down)", fontFamily: "var(--font-mono)" }}>
                            -₹{((totalExposure * 0.005) || 0).toFixed(0)}
                        </div>
                        <div style={{ fontSize: "0.62rem", color: "var(--accent-down)", fontWeight: 700 }}>-{(leverage * 0.5).toFixed(1)}% Risk</div>
                    </div>
                </div>
            </div>

            {/* Exchange Order Specs Strip */}
            {marginInfo && (
                <div style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.65rem",
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-mono)",
                    padding: "0 4px",
                }}>
                    <span>Tick: ₹{(marginInfo.tick_size / 100).toFixed(2)}</span>
                    <span>Lot: {marginInfo.lot_size}</span>
                    <span>Freeze Qty: {marginInfo.freeze_quantity?.toLocaleString("en-IN")}</span>
                    <span>Auto Square-Off: {marginInfo.cas_eligible ? "Enabled" : "Disabled"}</span>
                </div>
            )}
        </div>
    );
}
