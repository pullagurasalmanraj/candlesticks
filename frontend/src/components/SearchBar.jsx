import React, { memo, useRef, useEffect } from "react";
import { Search } from "lucide-react";
import StockLogo from "./StockLogo";

// Shared input style — used for all inputs/selects in this file
const inputStyle = {
    width:        "100%",
    height:       42,
    borderRadius: 999,
    border:       "1.5px solid var(--border-color)",
    background:   "var(--bg-secondary)",
    color:        "var(--text-primary)",
    padding:      "0 44px 0 40px",
    fontSize:     "0.9rem",
    fontFamily:   "var(--font-body)",
    outline:      "none",
    boxSizing:    "border-box",
    transition:   "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
    boxShadow:    "inset 0 1px 2px rgba(0,0,0,0.1)",
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
    const inputRef = useRef(null);
    const containerRef = useRef(null);

    useEffect(() => {
        const handleKeyDown = (e) => {
            if (
                (e.key === "/" && 
                 document.activeElement?.tagName !== "INPUT" && 
                 document.activeElement?.tagName !== "TEXTAREA") ||
                (e.key === "k" && (e.ctrlKey || e.metaKey))
            ) {
                e.preventDefault();
                inputRef.current?.focus();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, []);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (containerRef.current && !containerRef.current.contains(event.target)) {
                setShowResults(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        document.addEventListener("touchstart", handleClickOutside);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
            document.removeEventListener("touchstart", handleClickOutside);
        };
    }, [setShowResults]);

    return (
        <div ref={containerRef} style={{ width: "100%", maxWidth: 480, position: "relative" }}>

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
                    left:           14,
                    top:            "50%",
                    transform:      "translateY(-50%)",
                    color:          "var(--text-muted)",
                    pointerEvents:  "none",
                    display:        "flex",
                    alignItems:     "center",
                }}>
                    <Search size={16} />
                </span>
                <input
                    ref={inputRef}
                    value={search}
                    onChange={(e) => {
                        const val = e.target.value;
                        setSearch(val);
                        setShowResults(val.trim().length > 0);
                        if (!val.trim() && setDebouncedSearch) setDebouncedSearch("");
                    }}
                    onClick={() => {
                        if (search.trim().length > 0) setShowResults(true);
                    }}
                    placeholder="Search by symbol or name (e.g. TCS, INFY, RELIANCE)…"
                    style={inputStyle}
                    onFocus={e  => {
                        setShowResults(search.trim().length > 0);
                        e.target.style.borderColor = "var(--accent-blue)";
                        e.target.style.background = "var(--bg-tertiary)";
                        e.target.style.boxShadow = "0 0 14px var(--glow), inset 0 1px 2px rgba(0,0,0,0.05)";
                    }}
                    onBlur={e   => {
                        e.target.style.borderColor = "var(--border-color)";
                        e.target.style.background = "var(--bg-secondary)";
                        e.target.style.boxShadow = "inset 0 1px 2px rgba(0,0,0,0.1)";
                    }}
                />
                
                {/* Keyboard shortcut kbd */}
                {!search && (
                    <div style={{
                        position:       "absolute",
                        right:          14,
                        top:            "50%",
                        transform:      "translateY(-50%)",
                        background:     "var(--bg-tertiary)",
                        border:         "1px solid var(--border-color)",
                        borderRadius:   5,
                        padding:        "2px 6px",
                        fontSize:       "0.68rem",
                        fontFamily:     "var(--font-mono)",
                        color:          "var(--text-muted)",
                        pointerEvents:  "none",
                        display:        "flex",
                        alignItems:     "center",
                        gap:            2,
                        boxShadow:      "0 1px 2px rgba(0,0,0,0.1)",
                    }}>
                        <span style={{ fontSize: "0.58rem" }}>⌘</span>K
                    </div>
                )}

                {/* Reset button */}
                {search && (
                    <button
                        onClick={() => {
                            setSearch("");
                            setShowResults(false);
                            if (setDebouncedSearch) setDebouncedSearch("");
                            inputRef.current?.focus();
                        }}
                        style={{
                            position:       "absolute",
                            right:          14,
                            top:            "50%",
                            transform:      "translateY(-50%)",
                            border:         "none",
                            background:     "var(--border-color)",
                            color:          "var(--text-primary)",
                            cursor:         "pointer",
                            fontSize:       "0.7rem",
                            display:        "flex",
                            alignItems:     "center",
                            justifyContent: "center",
                            borderRadius:   "50%",
                            width:          18,
                            height:         18,
                            transition:     "all 0.15s ease",
                            padding:        0,
                            opacity:        0.8,
                        }}
                        onMouseEnter={e => {
                            e.currentTarget.style.opacity = 1;
                            e.currentTarget.style.background = "var(--accent-down)";
                        }}
                        onMouseLeave={e => {
                            e.currentTarget.style.opacity = 0.8;
                            e.currentTarget.style.background = "var(--border-color)";
                        }}
                    >
                        ✕
                    </button>
                )}
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
