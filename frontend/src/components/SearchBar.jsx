import React, { memo } from "react";
import StockLogo from "./StockLogo";

// Shared input style — used for all inputs/selects in this file
const inputStyle = {
    width:        "100%",
    height:       36,
    borderRadius: "var(--input-radius)",
    border:       "1px solid var(--border-color)",
    background:   "var(--bg-tertiary)",
    color:        "var(--text-primary)",
    padding:      "0 12px",
    fontSize:     "0.875rem",
    fontFamily:   "var(--font-body)",
    outline:      "none",
    boxSizing:    "border-box",
    transition:   "border-color 0.15s ease",
};

// memo() prevents SearchBar from re-rendering when Dashboard's other
// state changes (prices, activeSubscriptions, WebSocket status etc.)
// Only re-renders when its own props change.
const SearchBar = memo(function SearchBar({
    search,
    setSearch,
    setDebouncedSearch,
    showResults,
    setShowResults,
    debouncedSearch,
    instruments,
    watchlist,
    activeWatchlistCapLabel = "Watchlist",
    toggleWatchlist,
    setSelectedSymbol,
    setSelectedInstrument,
    setSelectedInstruments,
    getLtpForInstrument,
    prices,
}) {
    return (
        <div style={{ width: "100%", maxWidth: 480, position: "relative" }}>

            {/* Label */}
            <p style={{
                fontSize:      "0.65rem",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                color:         "var(--text-muted)",
                fontFamily:    "var(--font-body)",
                fontWeight:    600,
                marginBottom:  6,
            }}>
                Search Instruments
            </p>

            {/* Search input */}
            <div style={{ position: "relative" }}>
                <span style={{
                    position:       "absolute",
                    left:           12,
                    top:            "50%",
                    transform:      "translateY(-50%)",
                    fontSize:       12,
                    color:          "var(--text-muted)",
                    pointerEvents:  "none",
                }}>
                    🔍
                </span>
                <input
                    value={search}
                    onChange={(e) => {
                        const val = e.target.value;
                        setSearch(val);
                        setShowResults(val.trim().length > 0);
                        if (!val.trim() && setDebouncedSearch) setDebouncedSearch("");
                    }}
                    placeholder="Search by symbol or name (e.g. TCS, INFY, RELIANCE)…"
                    style={{
                        ...inputStyle,
                        height:       40,
                        borderRadius: 999,
                        paddingLeft:  36,
                        paddingRight: 16,
                    }}
                    onFocus={e  => e.target.style.borderColor = "var(--accent-blue)"}
                    onBlur={e   => e.target.style.borderColor = "var(--border-color)"}
                />
            </div>

            {/* Dropdown results */}
            {showResults && debouncedSearch && (
                <ul style={{
                    position:     "absolute",
                    top:          "calc(100% + 6px)",
                    left:         0,
                    width:        "100%",
                    maxHeight:    280,
                    overflowY:    "auto",
                    borderRadius: "var(--card-radius)",
                    border:       "1px solid var(--border-color)",
                    background:   "var(--bg-secondary)",
                    boxShadow:    "var(--shadow-card-hover)",
                    zIndex:       9999,
                    padding:      4,
                    margin:       0,
                    listStyle:    "none",
                }}>
                    {instruments.length === 0 ? (
                        <li style={{
                            padding:    "12px 14px",
                            fontSize:   "0.8rem",
                            color:      "var(--text-muted)",
                            fontStyle:  "italic",
                            fontFamily: "var(--font-body)",
                        }}>
                            No instruments found.
                        </li>
                    ) : (
                        instruments.slice(0, 80).map((inst) => {
                            const sym      = (inst.symbol || "").toUpperCase().trim();
                            const ltp      = getLtpForInstrument(inst, prices);
                            const inWatch  = watchlist.some((w) => w.symbol === sym);
                            const isOption = inst.segment === "NSE_FO" &&
                                ["CE", "PE"].includes(inst.instrument_type);

                            return (
                                <li
                                    key={`${sym}-${inst.instrument_key}`}
                                    style={{
                                        display:        "flex",
                                        alignItems:     "center",
                                        justifyContent: "space-between",
                                        padding:        "8px 10px",
                                        borderRadius:   8,
                                        cursor:         "pointer",
                                        transition:     "background 0.1s ease",
                                    }}
                                    onMouseEnter={e => e.currentTarget.style.background = "var(--bg-tertiary)"}
                                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                                    onClick={() => {
                                        const exchange = inst.exchange?.toUpperCase() || "";
                                        setSelectedSymbol(sym);
                                        const enriched = { ...inst, symbol: sym, exchange };
                                        setSelectedInstrument(enriched);
                                        setSelectedInstruments((prev) => {
                                            const exists = prev.some(
                                                (p) => p.symbol === sym && p.exchange === exchange
                                            );
                                            return exists ? prev : [...prev, enriched];
                                        });
                                        setShowResults(false);
                                    }}
                                >
                                    {/* Left — logo + symbol info */}
                                    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                                        <StockLogo symbol={sym} size={28} borderRadius={6} style={{ flexShrink: 0 }} />
                                        <div style={{ minWidth: 0 }}>
                                        <div style={{
                                            fontSize:     "0.8rem",
                                            fontWeight:   600,
                                            color:        "var(--text-primary)",
                                            fontFamily:   "var(--font-body)",
                                            display:      "flex",
                                            alignItems:   "center",
                                            gap:          6,
                                            overflow:     "hidden",
                                            textOverflow: "ellipsis",
                                            whiteSpace:   "nowrap",
                                        }}>
                                            {sym}
                                            {isOption && (
                                                <span style={{
                                                    fontSize:   "0.65rem",
                                                    color:      "var(--accent-blue)",
                                                    fontFamily: "var(--font-mono)",
                                                }}>
                                                    {inst.instrument_type} · Lot {inst.lot_size}
                                                </span>
                                            )}
                                        </div>

                                        <div style={{
                                            fontSize:     "0.7rem",
                                            color:        "var(--text-secondary)",
                                            fontFamily:   "var(--font-body)",
                                            overflow:     "hidden",
                                            textOverflow: "ellipsis",
                                            whiteSpace:   "nowrap",
                                            marginTop:    2,
                                        }}>
                                            {inst.name}
                                        </div>

                                        {isOption && (
                                            <div style={{
                                                fontSize:   "0.65rem",
                                                color:      "var(--text-muted)",
                                                fontFamily: "var(--font-mono)",
                                                marginTop:  2,
                                            }}>
                                                Exp: {new Date(inst.expiry).toLocaleDateString("en-IN", {
                                                    day: "2-digit", month: "short", year: "2-digit"
                                                })}
                                            </div>
                                        )}

                                        <div style={{
                                            fontSize:   "0.65rem",
                                            color:      "var(--text-muted)",
                                            fontFamily: "var(--font-mono)",
                                            marginTop:  1,
                                        }}>
                                            {inst.segment}
                                        </div>
                                    </div>
                                    </div>{/* close logo+info wrapper */}

                                    {/* Right — price + watchlist */}
                                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                                        <span style={{
                                            fontSize:   "0.78rem",
                                            fontWeight: 600,
                                            color:      "var(--text-primary)",
                                            fontFamily: "var(--font-mono)",
                                        }}>
                                            ₹{typeof ltp === "number" ? ltp.toLocaleString("en-IN") : "--"}
                                        </span>

                                        <button
                                            onClick={(e) => { e.stopPropagation(); toggleWatchlist(inst); }}
                                            title={`Toggle in ${activeWatchlistCapLabel}`}
                                            style={{
                                                fontSize:     "0.7rem",
                                                padding:      "2px 8px",
                                                borderRadius: 999,
                                                border:       inWatch
                                                    ? "1px solid var(--accent-gold)"
                                                    : "1px solid var(--border-color)",
                                                background:   inWatch ? "rgba(255,213,79,0.15)" : "transparent",
                                                color:        inWatch ? "var(--accent-gold)"    : "var(--text-muted)",
                                                cursor:       "pointer",
                                                fontFamily:   "var(--font-body)",
                                                transition:   "all 0.15s ease",
                                            }}
                                        >
                                            {inWatch ? "★" : "☆"}
                                        </button>
                                    </div>
                                </li>
                            );
                        })
                    )}
                </ul>
            )}
        </div>
    );
});

export default SearchBar;
