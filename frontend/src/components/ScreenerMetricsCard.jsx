import React, { useEffect, useState, useMemo } from "react";
import StockLogo from "./StockLogo";

// Smart Financial Currency & Value Formatter (Handles Crores, Percentages, and Numerical Scaling)
export function formatFinancialValue(val) {
    if (val === null || val === undefined || val === "") return "--";
    if (typeof val === "string" && (val.includes("₹") || val.includes("%") || val.includes("Cr"))) {
        return val;
    }
    const num = parseFloat(String(val).replace(/,/g, "").trim());
    if (isNaN(num)) return String(val);

    // If already in Crores (< 100,000,000) or raw integer (> 10,000,000)
    let crVal = num;
    if (Math.abs(num) >= 10000000) {
        crVal = num / 1e7;
    }

    const sign = crVal < 0 ? "-" : "";
    const absVal = Math.abs(crVal);

    if (absVal >= 10000) {
        return `${sign}₹${Math.round(absVal).toLocaleString("en-IN")} Cr`;
    } else if (absVal >= 100) {
        return `${sign}₹${absVal.toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} Cr`;
    } else if (absVal > 0) {
        return `${sign}₹${absVal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Cr`;
    } else {
        return "₹0.00 Cr";
    }
}

export default function ScreenerMetricsCard({ symbol, instrument, priceData, capCategory, onDataLoaded }) {
    const ltp = priceData?.ltp;
    const [fetchedData, setFetchedData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState("all");
    const [searchQuery, setSearchQuery] = useState("");

    const cleanSymbol = useMemo(() => {
        const s = symbol || instrument?.trading_symbol || instrument?.symbol || "";
        return s.replace(/^NSE_EQ\|/, "").replace(/-EQ$/, "").toUpperCase();
    }, [symbol, instrument]);

    // Live API Fetch from /api/screener-fundamentals/<symbol>
    useEffect(() => {
        if (!cleanSymbol) return;

        let isMounted = true;
        setLoading(true);

        fetch(`/api/fundamentals/${cleanSymbol}`)
            .then((res) => res.json())
            .then((resData) => {
                if (!isMounted) return;
                if (resData && resData.status === "success" && resData.data) {
                    setFetchedData(resData.data);
                    if (onDataLoaded) onDataLoaded(resData.data);
                } else {
                    setFetchedData(null);
                }
            })
            .catch((err) => {
                console.error("Failed to fetch Upstox fundamentals for", cleanSymbol, err);
                if (isMounted) setFetchedData(null);
            })
            .finally(() => {
                if (isMounted) setLoading(false);
            });

        return () => {
            isMounted = false;
        };
    }, [cleanSymbol, onDataLoaded]);

    // Derived Financial Metrics
    const data = useMemo(() => {
        const d = fetchedData || {};
        const currentLtp = typeof ltp === "number" ? ltp : (d.currentPrice ?? null);
        const pe = d.pe ?? null;
        const eps = d.eps ?? (pe && currentLtp ? +(currentLtp / pe).toFixed(2) : null);

        const mcap = d.marketCapCr || 0;
        const capLabel = d.capLabel || (mcap > 100000 ? "LARGE CAP" : mcap > 20000 ? "MID CAP" : mcap > 0 ? "SMALL CAP" : (capCategory ? capCategory.toUpperCase() + " CAP" : "EQUITY"));

        return {
            marketCapCr: d.marketCapCr ?? null,
            ltp: currentLtp,
            high52: d.high52 ?? null,
            low52: d.low52 ?? null,
            pe: pe,
            pb: d.pb ?? null,
            eps: eps,
            bv: d.bv ?? null,
            divYield: d.divYield ?? null,
            roce: d.roce ?? null,
            roe: d.roe ?? null,
            faceValue: d.faceValue ?? null,
            capLabel: capLabel,
            sector: d.sector || fetchedData?.profile?.sector || "NSE Equity",
            source: d.source || "Official Upstox Developer Fundamentals API (8/8 Endpoints)",
            isLive: Boolean(fetchedData),
        };
    }, [fetchedData, ltp, capCategory]);

    // EPS Yield % = (EPS / Stock Price) * 100
    const epsYieldPct = useMemo(() => {
        if (!data.eps || !data.ltp) return null;
        return ((data.eps / data.ltp) * 100).toFixed(2);
    }, [data.eps, data.ltp]);

    // 52-Week Range Percentage Position
    const rangePositionPct = useMemo(() => {
        if (!data.high52 || !data.low52 || !data.ltp) return 50;
        const totalRange = data.high52 - data.low52;
        if (totalRange <= 0) return 50;
        const currentDiff = data.ltp - data.low52;
        const pct = (currentDiff / totalRange) * 100;
        return Math.min(Math.max(pct, 0), 100);
    }, [data.high52, data.low52, data.ltp]);

    // Valuation Status Badge
    const valuationBadge = useMemo(() => {
        if (!data.pe) return { label: "VALUATION", color: "var(--accent-blue)" };
        if (data.pe < 15) return { label: "ATTRACTIVE / LOW P/E", color: "var(--accent-up)" };
        if (data.pe > 40) return { label: "HIGH GROWTH / PREMIUM", color: "#F59E0B" };
        return { label: "BALANCED VALUATION", color: "var(--accent-blue)" };
    }, [data.pe]);

    // All Metrics Structured Array
    const allMetrics = useMemo(() => [
        { id: "currentPrice", category: "valuation", label: "Current Market Price (LTP)", value: typeof data.ltp === "number" ? `₹${data.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "--", highlight: true, color: "var(--accent-up)", badgeText: "LIVE PRICE" },
        { id: "eps", category: "valuation", label: "EPS (Earnings Per Share)", value: data.eps ? `₹${data.eps}` : "--", highlight: true, color: "#10B981", badgeText: epsYieldPct ? `${epsYieldPct}% EPS Yield` : "EARNINGS" },
        { id: "pe", category: "valuation", label: "Stock Price to Earnings (P/E)", value: data.pe ? `${data.pe}x` : "--", highlight: true, color: "var(--accent-blue)", badgeText: valuationBadge.label },
        { id: "marketCap", category: "valuation", label: "Market Capitalization", value: data.marketCapCr ? `₹${data.marketCapCr.toLocaleString("en-IN")} Cr` : "--", highlight: true, color: "var(--text-primary)" },
        { id: "highLow52", category: "range", label: "52-Week High / Low", value: (data.high52 && data.low52) ? `₹${data.high52.toLocaleString("en-IN")} / ₹${data.low52.toLocaleString("en-IN")}` : "--" },
        { id: "roce", category: "profitability", label: "ROCE (Return on Capital)", value: typeof data.roce === "number" ? `${data.roce}%` : (data.roce ? `${data.roce}` : "--"), highlight: true, color: "var(--accent-up)", badgeText: "ROCE" },
        { id: "roe", category: "profitability", label: "ROE (Return on Equity)", value: typeof data.roe === "number" ? `${data.roe}%` : (data.roe ? `${data.roe}` : "--"), highlight: true, color: "var(--accent-up)", badgeText: "ROE" },
        { id: "bv", category: "valuation", label: "Book Value per Share", value: data.bv ? `₹${data.bv.toLocaleString("en-IN")}` : "--" },
        { id: "pb", category: "valuation", label: "Price to Book (P/B)", value: data.pb ? `${data.pb}x` : "--" },
        { id: "divYield", category: "range", label: "Dividend Yield", value: typeof data.divYield === "number" ? `${data.divYield}%` : (data.divYield || "--") },
        { id: "faceValue", category: "range", label: "Face Value", value: data.faceValue ? `₹${data.faceValue}` : "--" },
        { id: "capLabel", category: "range", label: "Market Cap Classification", value: data.capLabel, isCapBadge: true },
        { id: "sector", category: "range", label: "Industry & Sector", value: data.sector },
    ], [data, epsYieldPct, valuationBadge]);

    // Filtered Metrics by Category Tab & Search Query
    const filteredMetrics = useMemo(() => {
        return allMetrics.filter((m) => {
            const matchesTab = activeTab === "all" || m.category === activeTab;
            const matchesSearch = searchQuery === "" || m.label.toLowerCase().includes(searchQuery.toLowerCase());
            return matchesTab && matchesSearch;
        });
    }, [allMetrics, activeTab, searchQuery]);

    return (
        <div style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--card-radius)",
            boxShadow: "var(--shadow-card)",
            padding: "22px",
            display: "flex",
            flexDirection: "column",
            gap: 18,
            width: "100%",
        }}>
            {/* Header with Stock Logo & API Source Indicator */}
            <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                borderBottom: "1px solid var(--border-color)",
                paddingBottom: 14,
                gap: 12,
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <StockLogo symbol={cleanSymbol} size={42} borderRadius={10} />
                    <div>
                        <div style={{
                            fontSize: "0.68rem",
                            fontWeight: 700,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--accent-blue)",
                            fontFamily: "var(--font-body)",
                        }}>
                            Official Upstox Developer Fundamentals API Suite (8/8)
                        </div>
                        <div style={{
                            fontSize: "1.2rem",
                            fontWeight: 700,
                            fontFamily: "var(--font-display)",
                            color: "var(--text-primary)",
                            lineHeight: 1.2,
                        }}>
                            {cleanSymbol} Analytical Metrics
                        </div>
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {loading && (
                        <span style={{ fontSize: "0.72rem", color: "var(--accent-blue)", fontFamily: "var(--font-mono)" }}>
                            ⚡ Fetching Upstox API...
                        </span>
                    )}
                    <span style={{
                        fontSize: "0.68rem",
                        fontWeight: 700,
                        fontFamily: "var(--font-mono)",
                        background: "rgba(0, 230, 118, 0.12)",
                        color: "var(--accent-up)",
                        border: "1px solid rgba(0, 230, 118, 0.3)",
                        borderRadius: 6,
                        padding: "3px 10px",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                    }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: "var(--accent-up)",
                            display: "inline-block",
                            boxShadow: "0 0 6px var(--accent-up)"
                        }} />
                        Upstox Live Fundamentals
                    </span>
                </div>
            </div>

            {/* DYNAMIC HERO HIGHLIGHT BANNER (LTP, EPS, P/E, ROCE, Market Cap) */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                gap: 12,
                background: "linear-gradient(135deg, rgba(16, 185, 129, 0.08), rgba(59, 130, 246, 0.08))",
                border: "1px solid rgba(16, 185, 129, 0.25)",
                borderRadius: 12,
                padding: "16px",
            }}>
                {/* Hero LTP Price Card */}
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                        <span>📈 Live LTP Price</span>
                    </div>
                    <div style={{ fontSize: "1.4rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--accent-up)" }}>
                        {data.ltp ? `₹${data.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "--"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        Current Market Price
                    </div>
                </div>

                {/* Hero EPS Card */}
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                        <span>💵 EPS (TTM)</span>
                    </div>
                    <div style={{ fontSize: "1.4rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "#10B981" }}>
                        {data.eps ? `₹${data.eps}` : "--"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        {epsYieldPct ? `${epsYieldPct}% Yield` : "Annual Earnings"}
                    </div>
                </div>

                {/* Hero P/E Card */}
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                        📊 Stock P/E Multiple
                    </div>
                    <div style={{ fontSize: "1.4rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--accent-blue)" }}>
                        {data.pe ? `${data.pe}x` : "--"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: valuationBadge.color, fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                        {valuationBadge.label}
                    </div>
                </div>

                {/* Hero ROCE Card */}
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                        ⚡ ROCE Return %
                    </div>
                    <div style={{ fontSize: "1.4rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--accent-up)" }}>
                        {typeof data.roce === "number" ? `${data.roce}%` : (data.roce ? `${data.roce}` : "--")}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        Capital Efficiency
                    </div>
                </div>

                {/* Hero Market Cap Card */}
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <div style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                        🏢 Market Cap
                    </div>
                    <div style={{ fontSize: "1.2rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                        {data.marketCapCr ? `₹${(data.marketCapCr / 1000).toFixed(1)}k Cr` : "--"}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: "var(--accent-blue)", fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                        {data.capLabel}
                    </div>
                </div>
            </div>

            {/* 52-Week Price Range Position Bar */}
            {data.high52 && data.low52 && (
                <div style={{
                    background: "var(--bg-tertiary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 10,
                    padding: "12px 16px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                        <span>52W Low: ₹{data.low52.toLocaleString("en-IN")}</span>
                        <span style={{ color: "var(--text-primary)", fontWeight: 700 }}>52-Week Price Position</span>
                        <span>52W High: ₹{data.high52.toLocaleString("en-IN")}</span>
                    </div>

                    <div style={{
                        position: "relative",
                        height: 8,
                        background: "var(--bg-secondary)",
                        borderRadius: 4,
                        border: "1px solid var(--border-subtle)",
                        overflow: "hidden",
                    }}>
                        <div style={{
                            position: "absolute",
                            left: 0,
                            top: 0,
                            bottom: 0,
                            width: `${rangePositionPct}%`,
                            background: "linear-gradient(90deg, #3B82F6, #10B981)",
                            borderRadius: 4,
                            transition: "width 0.5s ease",
                        }} />
                    </div>
                </div>
            )}

            {/* DYNAMIC 8 UPSTOX API CATEGORY FILTER TABS & SEARCH INPUT */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {[
                            { id: "profile", label: "🏢 Profile" },
                            { id: "all", label: "📊 Key Ratios" },
                            { id: "shareholdings", label: "🍰 Shareholdings" },
                            { id: "income", label: "📈 Income Statement" },
                            { id: "balance", label: "🏛 Balance Sheet" },
                            { id: "cashflow", label: "💵 Cash Flow" },
                            { id: "actions", label: "🎁 Corporate Actions" },
                            { id: "competitors", label: "🥊 Competitors" },
                        ].map((t) => (
                            <button
                                key={t.id}
                                type="button"
                                onClick={() => setActiveTab(t.id)}
                                style={{
                                    background: activeTab === t.id ? "var(--accent-blue)" : "var(--bg-tertiary)",
                                    color: activeTab === t.id ? "#fff" : "var(--text-muted)",
                                    border: `1px solid ${activeTab === t.id ? "var(--accent-blue)" : "var(--border-color)"}`,
                                    borderRadius: 6,
                                    padding: "5px 11px",
                                    fontSize: "0.75rem",
                                    fontWeight: 600,
                                    cursor: "pointer",
                                    transition: "all 0.15s ease",
                                }}
                            >
                                {t.label}
                            </button>
                        ))}
                    </div>

                    {activeTab === "all" && (
                        <div style={{ position: "relative", minWidth: 160 }}>
                            <input
                                type="text"
                                placeholder="Filter ratios..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                style={{
                                    width: "100%",
                                    padding: "5px 10px 5px 26px",
                                    fontSize: "0.75rem",
                                    background: "var(--bg-tertiary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 6,
                                    color: "var(--text-primary)",
                                    outline: "none",
                                }}
                            />
                            <span style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", fontSize: "0.7rem", color: "var(--text-muted)" }}>
                                🔍
                            </span>
                        </div>
                    )}
                </div>

                {/* TAB 1: COMPANY PROFILE (/v2/fundamentals/{isin}/profile) */}
                {activeTab === "profile" && (() => {
                    const prof = fetchedData?.profile || {};
                    const desc = prof.company_profile || prof.description || prof.about;
                    const secMcap = prof.sector_market_cap_inr?.formatted || (prof.sector_market_cap_inr?.value ? `₹${prof.sector_market_cap_inr.value.toLocaleString("en-IN")} Cr` : null);
                    const secMcapUsd = prof.sector_market_cap_usd?.formatted || null;

                    return (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: 12,
                            background: "var(--bg-tertiary)", padding: "16px", borderRadius: 12, border: "1px solid var(--border-color)"
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    🏢 Official Company Profile ({cleanSymbol})
                                </div>
                                <span style={{ fontSize: "0.68rem", color: "var(--accent-blue)", fontFamily: "var(--font-mono)" }}>
                                    Upstox Profile API
                                </span>
                            </div>

                            {desc && (
                                <div style={{ fontSize: "0.8rem", lineHeight: 1.5, color: "var(--text-secondary)", background: "var(--bg-secondary)", padding: "12px 14px", borderRadius: 8, border: "1px solid var(--border-subtle)" }}>
                                    {desc}
                                </div>
                            )}

                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
                                {[
                                    { label: "Company Symbol", value: cleanSymbol },
                                    { label: "Industry Sector", value: prof.sector || data.sector },
                                    { label: "ISIN Code", value: fetchedData?.isin || "--" },
                                    { label: "Sector MCap (INR)", value: secMcap || "--" },
                                    { label: "Sector MCap (USD)", value: secMcapUsd || "--" },
                                    { label: "Classification", value: data.capLabel },
                                ].map((item, idx) => (
                                    <div key={idx} style={{ background: "var(--bg-secondary)", padding: "10px 12px", borderRadius: 8, border: "1px solid var(--border-subtle)" }}>
                                        <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginBottom: 2 }}>{item.label}</div>
                                        <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>{item.value}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    );
                })()}

                {/* TAB 2: KEY RATIOS (/v2/fundamentals/{isin}/key-ratios) */}
                {activeTab === "all" && (() => {
                    const upstoxRatios = Array.isArray(fetchedData?.keyRatios) ? fetchedData.keyRatios : [];

                    return (
                        <div style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: 2,
                            background: "var(--bg-tertiary)",
                            padding: "8px",
                            borderRadius: 12,
                            border: "1px solid var(--border-color)",
                        }}>
                            {/* Official Upstox Key Ratios comparison if available */}
                            {upstoxRatios.length > 0 && (
                                <div style={{
                                    display: "grid",
                                    gridTemplateColumns: "2fr 1fr 1fr",
                                    padding: "8px 14px",
                                    fontSize: "0.68rem",
                                    fontWeight: 700,
                                    color: "var(--text-muted)",
                                    fontFamily: "var(--font-mono)",
                                    borderBottom: "1px solid var(--border-subtle)",
                                    background: "rgba(255,255,255,0.02)",
                                    borderRadius: 6,
                                    marginBottom: 4,
                                }}>
                                    <div>Upstox Key Ratio</div>
                                    <div style={{ textAlign: "right", color: "var(--accent-up)" }}>Company Value</div>
                                    <div style={{ textAlign: "right", color: "var(--text-muted)" }}>Sector Average</div>
                                </div>
                            )}

                            {upstoxRatios.length > 0 ? (
                                upstoxRatios.map((item, idx) => (
                                    <div
                                        key={idx}
                                        style={{
                                            display: "grid",
                                            gridTemplateColumns: "2fr 1fr 1fr",
                                            alignItems: "center",
                                            padding: "10px 14px",
                                            background: idx % 2 === 0 ? "var(--bg-secondary)" : "transparent",
                                            borderRadius: 6,
                                        }}
                                    >
                                        <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                            {item.name}
                                        </span>
                                        <span style={{ textAlign: "right", fontSize: "0.92rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--accent-up)" }}>
                                            {item.company_value || "--"}
                                        </span>
                                        <span style={{ textAlign: "right", fontSize: "0.8rem", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                                            {item.sector_value || "--"}
                                        </span>
                                    </div>
                                ))
                            ) : (
                                filteredMetrics.map((item, idx, arr) => (
                                    <div
                                        key={item.id}
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "space-between",
                                            padding: "10px 14px",
                                            background: idx % 2 === 0 ? "var(--bg-secondary)" : "transparent",
                                            borderRadius: 6,
                                            borderBottom: idx < arr.length - 1 ? "1px solid var(--border-subtle)" : "none",
                                        }}
                                    >
                                        <div style={{
                                            fontSize: "0.82rem",
                                            fontWeight: 600,
                                            color: "var(--text-muted)",
                                            fontFamily: "var(--font-body)",
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 8,
                                        }}>
                                            <span>{item.label}</span>
                                        </div>
                                        <span style={{
                                            fontSize: "0.94rem",
                                            fontWeight: item.highlight ? 700 : 600,
                                            fontFamily: "var(--font-mono)",
                                            color: item.color || "var(--text-primary)",
                                        }}>
                                            {item.value}
                                        </span>
                                    </div>
                                ))
                            )}
                        </div>
                    );
                })()}

                {/* TAB 3: SHAREHOLDINGS (/v2/fundamentals/{isin}/share-holdings) */}
                {activeTab === "shareholdings" && (() => {
                    const shRaw = fetchedData?.shareHoldings;
                    let shCategories = [];
                    if (Array.isArray(shRaw)) shCategories = shRaw;
                    else if (Array.isArray(shRaw?.share_holdings)) shCategories = shRaw.share_holdings;
                    else if (Array.isArray(shRaw?.data)) shCategories = shRaw.data;

                    const colorMap = { promoters: "#10B981", promoter: "#10B981", fii: "#3B82F6", dii: "#8B5CF6", retail: "#F59E0B", public: "#F59E0B", government: "#06B6D4", others: "#6B7280" };
                    const getCatColor = (cat) => {
                        const c = String(cat || "").toLowerCase();
                        for (const [k, v] of Object.entries(colorMap)) { if (c.includes(k)) return v; }
                        return "#6B7280";
                    };

                    if (shCategories.length === 0) {
                        return (
                            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)", background: "var(--bg-tertiary)", borderRadius: 12, border: "1px solid var(--border-color)", fontSize: "0.85rem" }}>
                                🍰 No shareholding data returned by Upstox API for {cleanSymbol}.
                            </div>
                        );
                    }

                    return (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: 10,
                            background: "var(--bg-tertiary)", padding: "16px", borderRadius: 12, border: "1px solid var(--border-color)"
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    🍰 Shareholding Pattern & Ownership Structure ({cleanSymbol})
                                </div>
                                <span style={{ fontSize: "0.68rem", color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                                    Upstox API
                                </span>
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                {shCategories.map((sh, idx) => {
                                    const catName = sh.category || sh.name || "Category";
                                    const history = Array.isArray(sh.history) ? sh.history : [];
                                    const latestVal = history.length > 0 ? (history[0].value ?? history[0].percentage) : (sh.value ?? sh.percentage);
                                    const pctNum = parseFloat(String(latestVal || "0").replace("%", ""));
                                    const latestPeriod = history.length > 0 ? (history[0].period || history[0].year) : "";
                                    const barColor = getCatColor(catName);

                                    return (
                                        <div key={idx} style={{ background: "var(--bg-secondary)", borderRadius: 8, padding: "12px 14px" }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                    <div style={{ width: 10, height: 10, borderRadius: "50%", background: barColor, boxShadow: `0 0 6px ${barColor}55` }} />
                                                    <span style={{ fontSize: "0.82rem", fontWeight: 600, textTransform: "capitalize", color: "var(--text-primary)" }}>{sh.name || catName}</span>
                                                </div>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                    <span style={{ fontSize: "0.92rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: barColor }}>
                                                        {typeof pctNum === "number" && !isNaN(pctNum) ? `${pctNum.toFixed(2)}%` : String(latestVal || "--")}
                                                    </span>
                                                    {latestPeriod && (
                                                        <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{latestPeriod}</span>
                                                    )}
                                                </div>
                                            </div>
                                            <div style={{ height: 6, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
                                                <div style={{ height: "100%", width: `${Math.min(Math.max(pctNum, 0), 100)}%`, background: `linear-gradient(90deg, ${barColor}88, ${barColor})`, borderRadius: 3, transition: "width 0.5s ease" }} />
                                            </div>
                                            {history.length > 1 && (
                                                <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                                                    {history.slice(0, 5).map((h, hi) => (
                                                        <span key={hi} style={{
                                                            fontSize: "0.68rem", fontFamily: "var(--font-mono)",
                                                            color: hi === 0 ? barColor : "var(--text-muted)",
                                                            fontWeight: hi === 0 ? 700 : 400,
                                                            background: hi === 0 ? `${barColor}15` : "transparent",
                                                            padding: "1px 6px", borderRadius: 4,
                                                        }}>
                                                            {h.period || h.year}: {typeof h.value === "number" ? `${h.value.toFixed(1)}%` : (h.percentage ? `${h.percentage}%` : "--")}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })()}

                {/* TAB 4: INCOME STATEMENT (/v2/fundamentals/{isin}/income-statement) */}
                {activeTab === "income" && (() => {
                    const incRaw = fetchedData?.incomeStatement;
                    let incCategories = [];

                    // Prioritize full_statement if available so all detailed metrics (Revenue, Other Income, Total Revenue, Total Expenses, PBT, Tax, PAT, EPS) are rendered
                    if (Array.isArray(incRaw?.full_statement) && incRaw.full_statement.length > 0) {
                        incCategories = incRaw.full_statement;
                    } else if (Array.isArray(incRaw?.income_statement) && incRaw.income_statement.length > 0) {
                        incCategories = incRaw.income_statement;
                    } else if (Array.isArray(incRaw)) {
                        incCategories = incRaw;
                    }

                    if (incCategories.length === 0) {
                        return (
                            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)", background: "var(--bg-tertiary)", borderRadius: 12, border: "1px solid var(--border-color)", fontSize: "0.85rem" }}>
                                📈 No income statement data returned by Upstox API for {cleanSymbol}.
                            </div>
                        );
                    }

                    // Extract all unique period labels in chronological / reverse order
                    const allPeriods = [];
                    incCategories.forEach(cat => {
                        if (Array.isArray(cat.history)) {
                            cat.history.forEach(h => {
                                const p = h.period || h.year;
                                if (p && !allPeriods.includes(p)) allPeriods.push(p);
                            });
                        }
                    });

                    return (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: 12,
                            background: "var(--bg-tertiary)", padding: "16px", borderRadius: 12, border: "1px solid var(--border-color)"
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                                <div>
                                    <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                        📈 Profit & Loss / Income Statement ({cleanSymbol})
                                    </div>
                                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2 }}>
                                        Statement of Profit & Loss • {incRaw?.type ? incRaw.type.toUpperCase() : "CONSOLIDATED"} (Figures in ₹ Crores, EPS in ₹)
                                    </div>
                                </div>
                                <span style={{ fontSize: "0.68rem", color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                                    Upstox Official API ({incCategories.length} Line Items)
                                </span>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 6, overflowX: "auto" }}>
                                <div style={{
                                    display: "grid",
                                    gridTemplateColumns: `minmax(200px, 2fr) ${allPeriods.map(() => "minmax(95px, 1fr)").join(" ")}`,
                                    padding: "8px 12px",
                                    background: "rgba(255,255,255,0.03)",
                                    borderRadius: 6,
                                    fontSize: "0.72rem",
                                    fontWeight: 700,
                                    color: "var(--text-muted)",
                                    fontFamily: "var(--font-mono)",
                                }}>
                                    <div>Line Item / Metric</div>
                                    {allPeriods.map((p, i) => (
                                        <div key={i} style={{ textAlign: "right", color: i === 0 ? "var(--accent-blue)" : "inherit" }}>
                                            {p} {i === 0 && "(Latest)"}
                                        </div>
                                    ))}
                                </div>

                                {incCategories.map((cat, idx) => {
                                    const rowTitle = cat.particular || cat.category || cat.name || cat.metric || `Metric ${idx + 1}`;
                                    const lowerTitle = String(rowTitle).toLowerCase();
                                    const isKeyRow = ["total revenue", "revenue", "sales", "operating profit", "profit before tax", "profit after tax", "net profit", "pat", "eps"].some(k => lowerTitle === k || lowerTitle.includes(k));
                                    const isEps = lowerTitle.includes("eps");
                                    const historyMap = {};
                                    if (Array.isArray(cat.history)) {
                                        cat.history.forEach(h => { historyMap[h.period || h.year] = h; });
                                    }

                                    return (
                                        <div
                                            key={idx}
                                            style={{
                                                display: "grid",
                                                gridTemplateColumns: `minmax(200px, 2fr) ${allPeriods.map(() => "minmax(95px, 1fr)").join(" ")}`,
                                                padding: "10px 12px",
                                                background: isKeyRow ? "rgba(59,130,246,0.06)" : (idx % 2 === 0 ? "var(--bg-secondary)" : "transparent"),
                                                borderRadius: 6,
                                                borderLeft: isKeyRow ? "3px solid var(--accent-blue)" : "none",
                                                alignItems: "center",
                                            }}
                                        >
                                            <span style={{
                                                fontSize: "0.8rem",
                                                fontWeight: isKeyRow ? 700 : 500,
                                                textTransform: "capitalize",
                                                color: isKeyRow ? "var(--text-primary)" : "var(--text-secondary)",
                                            }}>
                                                {String(rowTitle).replace(/_/g, " ")}
                                            </span>

                                            {allPeriods.map((p, pi) => {
                                                const entry = historyMap[p];
                                                const val = entry ? (entry.value ?? entry.amount ?? entry.val) : null;
                                                let formatted = "--";
                                                if (val !== null && val !== undefined) {
                                                    if (isEps) {
                                                        formatted = `₹${parseFloat(val).toFixed(2)}`;
                                                    } else {
                                                        formatted = formatFinancialValue(val);
                                                    }
                                                }
                                                const isLatest = pi === 0;

                                                return (
                                                    <div key={pi} style={{ textAlign: "right" }}>
                                                        <div style={{
                                                            fontSize: isLatest ? "0.85rem" : "0.78rem",
                                                            fontWeight: isLatest ? 700 : 500,
                                                            fontFamily: "var(--font-mono)",
                                                            color: isLatest && isKeyRow ? "var(--accent-up)" : "var(--text-primary)",
                                                        }}>
                                                            {formatted}
                                                        </div>
                                                        {entry?.change && (
                                                            <div style={{
                                                                fontSize: "0.62rem",
                                                                fontFamily: "var(--font-mono)",
                                                                color: String(entry.change).startsWith("+") ? "var(--accent-up)" : "#EF4444",
                                                            }}>
                                                                {entry.change}
                                                            </div>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })()}

                {/* TAB 5: BALANCE SHEET (/v2/fundamentals/{isin}/balance-sheet) */}
                {activeTab === "balance" && (() => {
                    const bsRaw = fetchedData?.balanceSheet;
                    let bsRows = [];

                    // Prioritize full_statement if present so all line items (Equity, Liabilities, Assets) are shown
                    if (Array.isArray(bsRaw?.full_statement) && bsRaw.full_statement.length > 0) {
                        bsRows = bsRaw.full_statement;
                    } else if (Array.isArray(bsRaw?.history) && bsRaw.history.length > 0) {
                        const historyList = bsRaw.history;
                        bsRows = [
                            {
                                particular: "Total Assets",
                                history: historyList.map(h => ({ period: h.period, value: h.total_asset }))
                            },
                            {
                                particular: "Total Liabilities",
                                history: historyList.map(h => ({ period: h.period, value: h.total_liability }))
                            },
                            {
                                particular: "Net Worth / Equity",
                                history: historyList.map(h => ({ period: h.period, value: (h.total_asset && h.total_liability) ? (h.total_asset - h.total_liability) : null }))
                            },
                        ];
                    } else if (Array.isArray(bsRaw?.balance_sheet)) {
                        bsRows = bsRaw.balance_sheet;
                    } else if (Array.isArray(bsRaw)) {
                        bsRows = bsRaw;
                    }

                    if (bsRows.length === 0) {
                        return (
                            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)", background: "var(--bg-tertiary)", borderRadius: 12, border: "1px solid var(--border-color)", fontSize: "0.85rem" }}>
                                🏛 No balance sheet data returned by Upstox API for {cleanSymbol}.
                            </div>
                        );
                    }

                    const allPeriods = [];
                    bsRows.forEach(cat => {
                        if (Array.isArray(cat.history)) {
                            cat.history.forEach(h => {
                                const p = h.period || h.year;
                                if (p && !allPeriods.includes(p)) allPeriods.push(p);
                            });
                        }
                    });

                    return (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: 12,
                            background: "var(--bg-tertiary)", padding: "16px", borderRadius: 12, border: "1px solid var(--border-color)"
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div>
                                    <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                        🏛 Balance Sheet & Capital Structure ({cleanSymbol})
                                    </div>
                                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2 }}>
                                        Assets, Liabilities & Capital • {bsRaw?.type ? bsRaw.type.toUpperCase() : "CONSOLIDATED"} (Figures in ₹ Crores)
                                    </div>
                                </div>
                                <span style={{ fontSize: "0.68rem", color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                                    Upstox Official API ({bsRows.length} Line Items)
                                </span>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 6, overflowX: "auto" }}>
                                <div style={{
                                    display: "grid",
                                    gridTemplateColumns: `minmax(200px, 2fr) ${allPeriods.map(() => "minmax(95px, 1fr)").join(" ")}`,
                                    padding: "8px 12px",
                                    background: "rgba(255,255,255,0.03)",
                                    borderRadius: 6,
                                    fontSize: "0.72rem",
                                    fontWeight: 700,
                                    color: "var(--text-muted)",
                                    fontFamily: "var(--font-mono)",
                                }}>
                                    <div>Line Item</div>
                                    {allPeriods.map((p, i) => (
                                        <div key={i} style={{ textAlign: "right", color: i === 0 ? "var(--accent-blue)" : "inherit" }}>
                                            {p} {i === 0 && "(Latest)"}
                                        </div>
                                    ))}
                                </div>

                                {bsRows.map((cat, idx) => {
                                    const rowTitle = cat.particular || cat.name || cat.category || `Item ${idx + 1}`;
                                    const isTotal = ["total", "net worth", "equity", "asset", "liability"].some(k => String(rowTitle).toLowerCase().includes(k));
                                    const historyMap = {};
                                    if (Array.isArray(cat.history)) {
                                        cat.history.forEach(h => { historyMap[h.period || h.year] = h; });
                                    }

                                    return (
                                        <div
                                            key={idx}
                                            style={{
                                                display: "grid",
                                                gridTemplateColumns: `minmax(200px, 2fr) ${allPeriods.map(() => "minmax(95px, 1fr)").join(" ")}`,
                                                padding: "10px 12px",
                                                background: isTotal ? "rgba(16,185,129,0.06)" : (idx % 2 === 0 ? "var(--bg-secondary)" : "transparent"),
                                                borderRadius: 6,
                                                borderLeft: isTotal ? "3px solid #10B981" : "none",
                                                alignItems: "center",
                                            }}
                                        >
                                            <span style={{
                                                fontSize: "0.8rem",
                                                fontWeight: isTotal ? 700 : 500,
                                                color: "var(--text-primary)",
                                                textTransform: "capitalize",
                                            }}>
                                                {String(rowTitle).replace(/_/g, " ")}
                                            </span>

                                            {allPeriods.map((p, pi) => {
                                                const entry = historyMap[p];
                                                const val = entry ? (entry.value ?? entry.amount ?? entry.val) : null;
                                                const formatted = formatFinancialValue(val);

                                                return (
                                                    <div key={pi} style={{
                                                        textAlign: "right",
                                                        fontSize: pi === 0 ? "0.85rem" : "0.78rem",
                                                        fontWeight: pi === 0 ? 700 : 500,
                                                        fontFamily: "var(--font-mono)",
                                                        color: "var(--text-primary)",
                                                    }}>
                                                        {formatted}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })()}

                {/* TAB 6: CASH FLOW STATEMENT (/v2/fundamentals/{isin}/cash-flow) */}
                {activeTab === "cashflow" && (() => {
                    const cfRaw = fetchedData?.cashFlow;
                    let cfCategories = [];

                    // Prioritize full_statement if present
                    if (Array.isArray(cfRaw?.full_statement) && cfRaw.full_statement.length > 0) {
                        cfCategories = cfRaw.full_statement;
                    } else if (Array.isArray(cfRaw?.cash_flow) && cfRaw.cash_flow.length > 0) {
                        cfCategories = cfRaw.cash_flow;
                    } else if (Array.isArray(cfRaw)) {
                        cfCategories = cfRaw;
                    }

                    if (cfCategories.length === 0) {
                        return (
                            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)", background: "var(--bg-tertiary)", borderRadius: 12, border: "1px solid var(--border-color)", fontSize: "0.85rem" }}>
                                💵 No cash flow data returned by Upstox API for {cleanSymbol}.
                            </div>
                        );
                    }

                    const allPeriods = [];
                    cfCategories.forEach(cat => {
                        if (Array.isArray(cat.history)) {
                            cat.history.forEach(h => {
                                const p = h.period || h.year;
                                if (p && !allPeriods.includes(p)) allPeriods.push(p);
                            });
                        }
                    });

                    return (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: 12,
                            background: "var(--bg-tertiary)", padding: "16px", borderRadius: 12, border: "1px solid var(--border-color)"
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div>
                                    <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                        💵 Cash Flow Statement ({cleanSymbol})
                                    </div>
                                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2 }}>
                                        Operating, Investing & Financing Activities (Figures in ₹ Crores)
                                    </div>
                                </div>
                                <span style={{ fontSize: "0.68rem", color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                                    Upstox Official API ({cfCategories.length} Line Items)
                                </span>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 6, overflowX: "auto" }}>
                                <div style={{
                                    display: "grid",
                                    gridTemplateColumns: `minmax(200px, 2fr) ${allPeriods.map(() => "minmax(95px, 1fr)").join(" ")}`,
                                    padding: "8px 12px",
                                    background: "rgba(255,255,255,0.03)",
                                    borderRadius: 6,
                                    fontSize: "0.72rem",
                                    fontWeight: 700,
                                    color: "var(--text-muted)",
                                    fontFamily: "var(--font-mono)",
                                }}>
                                    <div>Activity / Line Item</div>
                                    {allPeriods.map((p, i) => (
                                        <div key={i} style={{ textAlign: "right", color: i === 0 ? "var(--accent-blue)" : "inherit" }}>
                                            {p} {i === 0 && "(Latest)"}
                                        </div>
                                    ))}
                                </div>

                                {cfCategories.map((cat, idx) => {
                                    const rowTitle = cat.particular || cat.name || (cat.category ? `${String(cat.category).replace(/_/g, " ")} Activities` : `Item ${idx + 1}`);
                                    const historyMap = {};
                                    if (Array.isArray(cat.history)) {
                                        cat.history.forEach(h => { historyMap[h.period || h.year] = h; });
                                    }

                                    return (
                                        <div
                                            key={idx}
                                            style={{
                                                display: "grid",
                                                gridTemplateColumns: `minmax(200px, 2fr) ${allPeriods.map(() => "minmax(95px, 1fr)").join(" ")}`,
                                                padding: "10px 12px",
                                                background: idx % 2 === 0 ? "var(--bg-secondary)" : "transparent",
                                                borderRadius: 6,
                                                alignItems: "center",
                                            }}
                                        >
                                            <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-primary)", textTransform: "capitalize" }}>
                                                {String(rowTitle).replace(/_/g, " ")}
                                            </span>

                                            {allPeriods.map((p, pi) => {
                                                const entry = historyMap[p];
                                                const val = entry ? (entry.value ?? entry.amount ?? entry.val) : null;
                                                const formatted = formatFinancialValue(val);

                                                return (
                                                    <div key={pi} style={{
                                                        textAlign: "right",
                                                        fontSize: pi === 0 ? "0.85rem" : "0.78rem",
                                                        fontWeight: pi === 0 ? 700 : 500,
                                                        fontFamily: "var(--font-mono)",
                                                        color: "var(--text-primary)",
                                                    }}>
                                                        {formatted}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })()}

                {/* TAB 7: CORPORATE ACTIONS (/v2/fundamentals/{isin}/corporate-actions) */}
                {activeTab === "actions" && (() => {
                    const caRaw = fetchedData?.corporateActions;
                    const caList = Array.isArray(caRaw) ? caRaw : [];

                    if (caList.length === 0) {
                        return (
                            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)", background: "var(--bg-tertiary)", borderRadius: 12, border: "1px solid var(--border-color)", fontSize: "0.85rem" }}>
                                🎁 No corporate actions or dividend announcements recorded by Upstox for {cleanSymbol}.
                            </div>
                        );
                    }

                    return (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: 10,
                            background: "var(--bg-tertiary)", padding: "16px", borderRadius: 12, border: "1px solid var(--border-color)"
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    🎁 Dividends, Splits & Corporate Events ({cleanSymbol})
                                </div>
                                <span style={{ fontSize: "0.68rem", color: "var(--accent-up)", fontFamily: "var(--font-mono)" }}>
                                    Upstox API
                                </span>
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                {caList.map((ca, idx) => {
                                    const actionType = ca.name || ca.action_type || "Dividend";
                                    const exDate = ca.expiry_date || ca.ex_date || "--";
                                    const details = Array.isArray(ca.event_details) ? ca.event_details : [];

                                    return (
                                        <div key={idx} style={{
                                            display: "flex", flexDirection: "column", gap: 8,
                                            padding: "12px 14px", background: "var(--bg-secondary)", borderRadius: 8,
                                            border: "1px solid var(--border-subtle)",
                                        }}>
                                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                                    <div style={{
                                                        fontSize: "0.68rem", fontWeight: 700, fontFamily: "var(--font-mono)",
                                                        background: "rgba(16,185,129,0.15)",
                                                        color: "#10B981",
                                                        border: "1px solid rgba(16,185,129,0.3)",
                                                        borderRadius: 4, padding: "2px 8px", textTransform: "uppercase"
                                                    }}>
                                                        {actionType}
                                                    </div>
                                                    <div>
                                                        <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                                            {actionType} - {cleanSymbol}
                                                        </div>
                                                        <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                                                            Ex-Date: {exDate}
                                                        </div>
                                                    </div>
                                                </div>
                                                {ca.amount && (
                                                    <div style={{ fontSize: "1.1rem", fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--accent-up)" }}>
                                                        ₹{ca.amount}
                                                    </div>
                                                )}
                                            </div>

                                            {details.length > 0 && (
                                                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", borderTop: "1px solid rgba(255,255,255,0.04)", paddingTop: 6 }}>
                                                    {details.map((d, di) => (
                                                        <span key={di} style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                                                            <strong>{d.name}:</strong> {d.value}
                                                        </span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })()}

                {/* TAB 8: PEER COMPETITORS (/v2/fundamentals/{instrument_key}/competitors) */}
                {activeTab === "competitors" && (() => {
                    const compList = Array.isArray(fetchedData?.competitors) ? fetchedData.competitors : [];

                    if (compList.length === 0) {
                        return (
                            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)", background: "var(--bg-tertiary)", borderRadius: 12, border: "1px solid var(--border-color)", fontSize: "0.85rem" }}>
                                🥊 No peer competitors returned by Upstox API for {cleanSymbol}.
                            </div>
                        );
                    }

                    return (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: 10,
                            background: "var(--bg-tertiary)", padding: "16px", borderRadius: 12, border: "1px solid var(--border-color)"
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                <div>
                                    <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                        🥊 Peer Competitors ({data.sector})
                                    </div>
                                    <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2 }}>
                                        Live Upstox Competitor Peers for {cleanSymbol}
                                    </div>
                                </div>
                                <span style={{
                                    fontSize: "0.68rem",
                                    fontWeight: 700,
                                    color: "var(--accent-up)",
                                    fontFamily: "var(--font-mono)",
                                    background: "rgba(0,230,118,0.12)",
                                    border: "1px solid rgba(0,230,118,0.3)",
                                    borderRadius: 6,
                                    padding: "3px 8px",
                                }}>
                                    Live Upstox API
                                </span>
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                {compList.map((comp, idx) => {
                                    const sym = comp.trading_symbol || "PEER";
                                    const companyName = comp.name || sym;

                                    return (
                                        <div key={idx} style={{
                                            display: "flex", flexDirection: "column", gap: 6,
                                            padding: "12px 14px", background: "var(--bg-secondary)", borderRadius: 8,
                                            border: "1px solid var(--border-subtle)",
                                        }}>
                                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                                    <div style={{
                                                        width: 26, height: 26, borderRadius: 6,
                                                        background: "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(99,102,241,0.18))",
                                                        display: "flex", alignItems: "center", justifyContent: "center",
                                                        fontSize: "0.72rem", fontWeight: 800, color: "var(--accent-blue)",
                                                    }}>
                                                        {idx + 1}
                                                    </div>
                                                    <StockLogo symbol={sym} size={32} borderRadius={6} />
                                                    <div>
                                                        <div style={{ fontSize: "0.88rem", fontWeight: 700, color: "var(--text-primary)" }}>{sym}</div>
                                                        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{companyName}</div>
                                                    </div>
                                                </div>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                    {comp.marketCapCr && (
                                                        <span style={{ fontSize: "0.78rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--accent-up)" }}>
                                                            {comp.marketCapCr}
                                                        </span>
                                                    )}
                                                    <span style={{
                                                        fontSize: "0.65rem", fontWeight: 700, fontFamily: "var(--font-mono)",
                                                        background: "rgba(16,185,129,0.12)", color: "#10B981",
                                                        border: "1px solid rgba(16,185,129,0.3)", borderRadius: 4, padding: "2px 8px",
                                                    }}>
                                                        NSE
                                                    </span>
                                                </div>
                                            </div>

                                            {comp.profile && (
                                                <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", lineHeight: 1.4, marginTop: 2 }}>
                                                    {comp.profile}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })()}
            </div>
        </div>
    );
}
