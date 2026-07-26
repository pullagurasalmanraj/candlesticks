// src/pages/Dashboard.jsx
import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";
import { useTheme } from "../context/ThemeContext";
import SkeletonLoader from "../components/SkeletonLoader";

import { INDEX_DEFAULTS, INDEX_NAME_TO_SYMBOL } from "../context/indexes";
import { normalizeKey } from "../utils/instrumentUtils";
import { getLtpForInstrument } from "../utils/priceUtils";
import { formatYMD } from "../utils/dateUtils";
import { startOfDay } from "../utils/dateUtils";
import {
    DEFAULT_WATCHLIST_CAP,
    WATCHLIST_CAP_KEYS,
    WATCHLIST_CAP_OPTIONS,
    WATCHLIST_LEGACY_KEY,
    WATCHLIST_STORAGE_KEY,
    ensureWatchlistsShape,
    findWatchlistCapBySymbol,
    flattenWatchlistsByCap,
    getWatchlistCapLabel,
    normalizeSymbol,
    readPreferredWatchlistCap,
    readStoredWatchlistsByCap,
    savePreferredWatchlistCap,
} from "../utils/watchlistUtils";

import SearchBar from "../components/SearchBar";
import WebSocketStatus from "../components/WebSocketStatus";
import MarketSummary from "../components/MarketSummary";
import IndexStrip from "../components/IndexStrip";
import SelectedInstruments from "../components/SelectedInstruments";
import ToolsPanel from "../components/ToolsPanel";
import ProfileDrawer, { Avatar } from "../components/ProfileDrawer";
import StockLogo from "../components/StockLogo";
import useInstrumentSearch from "../hooks/useInstrumentSearch";
import useWebSocketPrices from "../hooks/useWebSocketPrices.js";
import { fetchTimeframes } from "../services/timeframeService";
import { fetchHistoricalCandlesAPI } from "../services/candleService";
import { subscribeSymbol, unsubscribeAllInstruments, unsubscribeInstrument } from "../services/subscriptionService";
import { generateIndicators } from "../services/indicatorService";
import { downloadExcelAPI } from "../services/exportService";

// ── Section header component ─────────────────────────────────────
function SectionHeader({ title, subtitle, action }) {
    return (
        <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 14,
        }}>
            <div>
                <div style={{
                    fontSize: "0.7rem",
                    fontWeight: 700,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: "var(--text-muted)",
                    fontFamily: "var(--font-body)",
                    marginBottom: 3,
                }}>
                    {subtitle}
                </div>
                <div style={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    fontFamily: "var(--font-display)",
                    color: "var(--text-primary)",
                    letterSpacing: "-0.01em",
                }}>
                    {title}
                </div>
            </div>
            {action}
        </div>
    );
}

// ── Panel card wrapper ───────────────────────────────────────────
function Panel({ children, style = {} }) {
    return (
        <div style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--card-radius)",
            boxShadow: "var(--shadow-card)",
            padding: "20px",
            ...style,
        }}>
            {children}
        </div>
    );
}

function normalizeIndexSnapshot(row) {
    const ltp = Number(row?.ltp);
    const change = Number(row?.change);
    const percent = Number(row?.percent);

    return {
        ltp: Number.isFinite(ltp) ? ltp : "--",
        change: Number.isFinite(change) ? change : 0,
        percent: Number.isFinite(percent) ? percent : 0,
    };
}

function readStoredArray(key) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function readStoredObject(key) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? parsed : {};
    } catch {
        return {};
    }
}

export default function Dashboard() {
    const { theme } = useTheme();

    // ── State ────────────────────────────────────────────────────
    const [selectedInstruments, setSelectedInstruments] = useState(() => readStoredArray("selectedInstruments"));
    const [isApplyingIndicators, setIsApplyingIndicators] = useState(false);
    const [watchlistsByCap, setWatchlistsByCap] = useState(() => readStoredWatchlistsByCap());
    const [activeWatchlistCap, setActiveWatchlistCap] = useState(() => readPreferredWatchlistCap());
    const [selectedSymbol, setSelectedSymbol] = useState("");
    const [selectedInstrument, setSelectedInstrument] = useState(null);
    const [activeSubscriptions, setActiveSubscriptions] = useState(() => readStoredObject("activeSubscriptions"));
    const [startDate, setStartDate] = useState(null);
    const [endDate, setEndDate] = useState(null);
    const [timeframes, setTimeframes] = useState([]);
    const [timeframe, setTimeframe] = useState("");
    const [histStart, setHistStart] = useState(null);
    const [histEnd, setHistEnd] = useState(null);
    const [isFetchingHistory, setIsFetchingHistory] = useState(false);
    const [years, setYears] = useState("");
    const [indexData, setIndexData] = useState({});
    const [marketSummary, setMarketSummary] = useState(null);
    const [asOf, setAsOf] = useState(null);
    const [toast, setToastState] = useState(null);
    const [activePanel, setActivePanel] = useState("instruments");
    const [profileOpen, setProfileOpen] = useState(false); // "instruments" | "tools"
    const [operationResult, setOperationResult] = useState(null);
    const [force, setForce] = useState(false);
    // Removed local storageDownloadedRegistry to ensure manual DB deletes are immediately respected

    const setToast = useCallback((val) => {
        if (!val) {
            setToastState(null);
            return;
        }
        let message = "";
        let type = "info";
        if (typeof val === "object") {
            message = val.message || "";
            type = val.type || "info";
        } else {
            message = String(val);
            const lower = message.toLowerCase();
            if (lower.includes("success") || lower.includes("done") || lower.includes("saved") || lower.includes("stored") || lower.includes("subscribed") || lower.includes("downloaded") || lower.includes("complete")) {
                type = "success";
            } else if (lower.includes("error") || lower.includes("failed") || lower.includes("missing") || lower.includes("select a") || lower.includes("invalid") || lower.includes("require")) {
                type = "error";
            } else if (lower.includes("generating") || lower.includes("fetching") || lower.includes("loading") || lower.includes("applying")) {
                type = "loading";
            }
        }
        setToastState({ message, type, id: Date.now() });
    }, []);

    const {
        search, setSearch, debouncedSearch,
        instruments, showResults, setShowResults
    } = useInstrumentSearch();
    const watchlist = useMemo(() => flattenWatchlistsByCap(watchlistsByCap), [watchlistsByCap]);
    const activeWatchlist = watchlistsByCap[activeWatchlistCap] || [];
    const activeWatchlistLabel = useMemo(
        () => getWatchlistCapLabel(activeWatchlistCap),
        [activeWatchlistCap]
    );
    const watchlistCountByCap = useMemo(() => {
        const safe = ensureWatchlistsShape(watchlistsByCap);
        const counts = {};
        WATCHLIST_CAP_KEYS.forEach((cap) => {
            counts[cap] = safe[cap].length;
        });
        return counts;
    }, [watchlistsByCap]);

    // ── Init ─────────────────────────────────────────────────────
    useEffect(() => { setIndexData(INDEX_DEFAULTS); }, []);
    useEffect(() => {
        if (!toast) return;
        if (toast.type === "loading") return;
        const t = setTimeout(() => setToastState(null), 3000);
        return () => clearTimeout(t);
    }, [toast]);
    useEffect(() => {
        // Restore backend subscriptions for active subscriptions on mount (persists across page refresh)
        let cancelled = false;
        const keys = Object.keys(activeSubscriptions);
        if (keys.length > 0) {
            (async () => {
                try {
                    await subscribeInstruments(keys);
                } catch {
                    // keep UI usable even if subscription endpoint is temporarily unavailable
                }
            })();
        }
        return () => { cancelled = true; };
    }, []);
    useEffect(() => {
        let cancelled = false;

        const loadIndexSummary = async () => {
            try {
                const res = await fetch("/api/index-summary");
                if (!res.ok) return;

                const payload = await res.json();
                if (cancelled) return;

                const nextIndexData = { ...INDEX_DEFAULTS };
                const payloadIndices = payload?.indices || {};

                Object.entries(payloadIndices).forEach(([name, row]) => {
                    const symbol = INDEX_NAME_TO_SYMBOL[name];
                    if (!symbol) return;
                    nextIndexData[symbol] = normalizeIndexSnapshot(row);
                });

                setIndexData((prev) => ({ ...prev, ...nextIndexData }));
                setMarketSummary(payload?.marketSummary || null);
                setAsOf(payload?.asOf || null);
            } catch {
                // websocket live ticks still drive the strip
            }
        };

        loadIndexSummary();
        const pollId = setInterval(loadIndexSummary, 30000);

        return () => {
            cancelled = true;
            clearInterval(pollId);
        };
    }, []);

    // ── Instrument maps ──────────────────────────────────────────
    const instrumentByKey = useMemo(() => {
        const map = {};
        instruments.forEach((inst) => {
            const key = inst.instrument_key?.trim().toUpperCase();
            if (key) map[key] = inst;
        });
        return map;
    }, [instruments]);

    const { prices, isConnected, isLoading, connectWebSocket, disconnectWebSocket } = useWebSocketPrices(instrumentByKey);

    // Stable references — memo on WebSocketStatus only works if these
    // don't get recreated on every render from search keystrokes
    const stableConnect = useCallback(() => connectWebSocket?.(), [connectWebSocket]);
    const stableDisconnect = useCallback(() => disconnectWebSocket?.(), [disconnectWebSocket]);

    // ── Persist ──────────────────────────────────────────────────
    useEffect(() => {
        try { localStorage.setItem("selectedInstruments", JSON.stringify(selectedInstruments)); }
        catch { }
    }, [selectedInstruments]);
    useEffect(() => {
        try { localStorage.setItem("activeSubscriptions", JSON.stringify(activeSubscriptions)); }
        catch { }
    }, [activeSubscriptions]);
    useEffect(() => {
        savePreferredWatchlistCap(activeWatchlistCap);
    }, [activeWatchlistCap]);
    useEffect(() => {
        try {
            localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(watchlistsByCap));
            localStorage.setItem(WATCHLIST_LEGACY_KEY, JSON.stringify(watchlist));
        }
        catch { }
    }, [watchlistsByCap, watchlist]);

    // ── Load timeframes ──────────────────────────────────────────
    useEffect(() => {
        let mounted = true;
        async function load() {
            try {
                const data = await fetchTimeframes();
                if (mounted) setTimeframes(data);
            } catch { if (mounted) setTimeframes([]); }
        }
        load();
        return () => { mounted = false; };
    }, []);

    // ── Handlers (useCallback — prevents SearchBar re-render on keystroke)
    const subscribeToStock = useCallback(async (inst) => {
        if (!inst) return;
        const key = inst.instrument_key?.trim();
        const sym = inst.symbol?.toUpperCase().trim();
        const isActive = !!activeSubscriptions[key];
        if (!key) return setToast("Missing instrument key.");
        try {
            if (!isActive) {
                await subscribeSymbol(key);
                setActiveSubscriptions((prev) => ({ ...prev, [key]: true }));
                setSelectedSymbol(sym);
                setSelectedInstrument(inst);
                setToast(`Subscribed: ${sym}`);
            } else {
                await unsubscribeInstrument(key);
                setActiveSubscriptions((prev) => { const u = { ...prev }; delete u[key]; return u; });
                setToast(`Unsubscribed: ${sym}`);
            }
        } catch { setToast("Failed to update subscription"); }
    }, [activeSubscriptions]);

    const toggleWatchlist = useCallback((inst) => {
        const sym = normalizeSymbol(inst?.symbol);
        if (!sym) return;

        setWatchlistsByCap((prevRaw) => {
            const prev = ensureWatchlistsShape(prevRaw);
            const next = {};
            WATCHLIST_CAP_KEYS.forEach((cap) => {
                next[cap] = [...prev[cap]];
            });

            const existingCap = findWatchlistCapBySymbol(prev, sym);
            if (existingCap === activeWatchlistCap) {
                next[existingCap] = next[existingCap].filter((item) => item.symbol !== sym);
                return next;
            }

            if (existingCap) {
                next[existingCap] = next[existingCap].filter((item) => item.symbol !== sym);
            }

            next[activeWatchlistCap].push({
                ...inst,
                symbol: sym,
                cap: activeWatchlistCap,
            });
            return next;
        });
    }, [activeWatchlistCap]);

    const applyIndicators = async () => {
        if (!selectedSymbol || !timeframe) return setToast("Select a symbol and timeframe first.");
        setIsApplyingIndicators(true);
        try {
            setToast(force ? "Force recalculating indicators & signals..." : "Generating indicators...");
            const t0 = performance.now();
            const data = await generateIndicators(selectedSymbol, timeframe, force);
            const elapsedMs = data.execution_time_ms ? data.execution_time_ms : (performance.now() - t0).toFixed(1);
            const timeStr = elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(2)}s` : `${elapsedMs}ms`;
            const isCached = Boolean(data.db_validated);

            setToast(isCached ? `⚡ DB Cache (${timeStr}): Loaded ${data.rows || 0} rows` : `Saved ${data.count || data.rows || 0} rows for ${selectedSymbol} in ${timeStr}`);
            setOperationResult({
                title: isCached ? `Indicators Loaded from DB Cache (${timeStr})` : `Indicators Generated & Saved (${timeStr})`,
                type: "indicators",
                symbol: selectedSymbol,
                timeframe: timeframe === "1440" ? "1D" : timeframe,
                rows: data.count || data.rows || 0,
                fromDate: data.from_date || "N/A",
                toDate: data.to_date || "N/A",
                dbValidated: isCached,
                duration: timeStr,
                message: data.message
            });
        } catch (err) { setToast(err.message || "Error"); }
        finally { setIsApplyingIndicators(false); }
    };

    const fetchHistoricalCandles = async () => {
        if (!selectedSymbol || !timeframe || !histStart || !histEnd)
            return setToast("Select symbol, timeframe and date range.");
        if (!selectedInstrument) return setToast("Select from search list first.");

        setIsFetchingHistory(true);
        const t0 = performance.now();
        try {
            if (!force) {
                const checkRes = await fetch("/api/candles/check", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        symbol: selectedSymbol,
                        instrument_key: selectedInstrument.instrument_key,
                        timeframe
                    })
                });
                const check = await checkRes.json();
                if (check.exists) {
                    const elapsedMs = (performance.now() - t0).toFixed(1);
                    const timeStr = elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(2)}s` : `${elapsedMs}ms`;
                    setToast(`⚡ DB Cache (${timeStr}): Candles already present`);
                    setOperationResult({
                        title: `Candles Already Present (${timeStr})`,
                        type: "candles",
                        symbol: selectedSymbol,
                        timeframe: timeframe === "1440" ? "1D" : timeframe,
                        rows: check.count,
                        fromDate: formatYMD(histStart),
                        toDate: formatYMD(histEnd),
                        already_exists: true,
                        duration: timeStr
                    });
                    setIsFetchingHistory(false);
                    return;
                }
            }

            const r = await fetchHistoricalCandlesAPI({
                symbol: selectedSymbol, instrument_key: selectedInstrument.instrument_key,
                timeframe, histStart, histEnd, force
            });
            const elapsedMs = (performance.now() - t0).toFixed(1);
            const timeStr = elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(2)}s` : `${elapsedMs}ms`;
            if (r.already_exists) {
                setToast(`⚡ DB Cache (${timeStr}): Candles already present`);
            } else {
                setToast(`🚀 Stored ${r.inserted} candles in ${timeStr}`);
            }
            setOperationResult({
                title: r.already_exists ? `Candles Already Present (${timeStr})` : `Candles Fetched & Stored (${timeStr})`,
                type: "candles",
                symbol: selectedSymbol,
                timeframe: timeframe === "1440" ? "1D" : timeframe,
                rows: r.already_exists ? r.total : r.inserted,
                fromDate: r.from_date || formatYMD(histStart),
                toDate: r.to_date || formatYMD(histEnd),
                already_exists: !!r.already_exists,
                duration: timeStr
            });
        } catch (err) { setToast(err.message); }
        finally { setIsFetchingHistory(false); }
    };

    const runBulkFetch = async () => {
        if (!selectedInstrument) return setToast("Select stock first.");
        if (!years) return setToast("Select a year range.");
        const sym = selectedSymbol.toUpperCase();
        const key = selectedInstrument.instrument_key;
        const months = years * 12;

        setIsFetchingHistory(true);
        const t0 = performance.now();
        try {
            if (!force) {
                const checkRes = await fetch("/api/candles/check", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        symbol: sym,
                        instrument_key: key,
                        timeframe
                    })
                });
                const check = await checkRes.json();
                if (check.exists) {
                    const elapsedMs = (performance.now() - t0).toFixed(1);
                    const timeStr = elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(2)}s` : `${elapsedMs}ms`;
                    setToast(`⚡ DB Cache (${timeStr}): All data already present.`);
                    let today = new Date();
                    let finalEndDate = formatYMD(new Date(today.getFullYear(), today.getMonth() + 1, 0));
                    let finalStartDate = formatYMD(new Date(today.getFullYear() - years, today.getMonth(), 1));
                    setOperationResult({
                        title: `Bulk Fetch Bypassed (${timeStr})`,
                        type: "candles",
                        symbol: sym,
                        timeframe: timeframe === "1440" ? "1D" : timeframe,
                        rows: check.count,
                        fromDate: finalStartDate,
                        toDate: finalEndDate,
                        duration: `${years} Year(s) (${timeStr})`,
                        already_exists: true,
                        skippedChunks: months,
                        totalChunks: months
                    });
                    setIsFetchingHistory(false);
                    return;
                }
            }

            let today = new Date(), year = today.getFullYear(), month = today.getMonth();
            setToast(`Fetching ${years} year(s)...`);
            let totalInserted = 0;
            let totalSkippedMonths = 0;
            let totalExisting = 0;
            let finalEndDate = formatYMD(new Date(year, month + 1, 0));
            let finalStartDate = "";
            for (let i = 0; i < months; i++) {
                const start = new Date(year, month, 1);
                const end = new Date(year, month + 1, 0);
                if (i === months - 1) {
                    finalStartDate = formatYMD(start);
                }
                const r = await fetchHistoricalCandlesAPI({ symbol: sym, instrument_key: key, timeframe, histStart: start, histEnd: end, force });
                if (r.already_exists) {
                    totalSkippedMonths++;
                    totalExisting += (r.total || 0);
                    setToast(`Already present: ${formatYMD(start)} → ${formatYMD(end)}`);
                } else {
                    totalInserted += (r.inserted || 0);
                    setToast(`Stored ${formatYMD(start)} → ${formatYMD(end)}`);
                }
                month--;
                if (month < 0) { month = 11; year--; }
                await new Promise(r => setTimeout(r, 300));
            }
            const elapsedMs = (performance.now() - t0).toFixed(1);
            const timeStr = elapsedMs >= 1000 ? `${(elapsedMs / 1000).toFixed(2)}s` : `${elapsedMs}ms`;
            const allSkipped = totalSkippedMonths === months;
            if (allSkipped) {
                setToast(`⚡ DB Cache (${timeStr}): All data already present.`);
            } else {
                setToast(`🚀 Done fetching ${years} year(s) in ${timeStr}.`);
            }
            setOperationResult({
                title: allSkipped ? `Bulk Fetch Bypassed (${timeStr})` : `Bulk Candle Fetch Completed (${timeStr})`,
                type: "candles",
                symbol: sym,
                timeframe: timeframe === "1440" ? "1D" : timeframe,
                rows: allSkipped ? totalExisting : totalInserted,
                fromDate: finalStartDate,
                toDate: finalEndDate,
                duration: `${years} Year(s) (${timeStr})`,
                already_exists: allSkipped,
                skippedChunks: totalSkippedMonths,
                totalChunks: months
            });
        } catch (err) { setToast(err.message); }
        finally { setIsFetchingHistory(false); }
    };

    const downloadExcel = async () => {
        if (!selectedSymbol || !startDate || !endDate) return setToast("Select symbol, start and end date.");
        if (!selectedInstrument) return setToast("Select stock from search list first.");
        const key = selectedInstrument.instrument_key;
        if (!key) return setToast("No instrument_key found.");
        try {
            const blob = await downloadExcelAPI({ instrument_key: key, symbol: selectedSymbol.trim().toUpperCase(), startDate, endDate });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `${selectedSymbol}_data.xlsx`;
            document.body.appendChild(a); a.click(); a.remove();
            setToast("Excel downloaded.");
        } catch (err) { setToast(err.message || "Failed to download."); }
    };

    if (isLoading) {
        return (
            <div style={{ minHeight: "calc(100vh - var(--navbar-height))", background: "var(--bg-primary)" }}>
                <SkeletonLoader />
            </div>
        );
    }

    const user = localStorage.getItem("user") || "Trader";
    const initials = user.slice(0, 2).toUpperCase();
    const hour = new Date().getHours();
    const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

    // ── UI ───────────────────────────────────────────────────────
    return (
        <div style={{
            minHeight: "calc(100vh - var(--navbar-height))",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
        }}>
            <style>{`
                @keyframes fadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }
                @keyframes scaleIn {
                    from { transform: scale(0.95); opacity: 0; }
                    to { transform: scale(1); opacity: 1; }
                }
                @keyframes toastSlideIn {
                    from { transform: translateX(120%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes toastSpin {
                    to { transform: rotate(360deg); }
                }
                @keyframes toastProgress {
                    from { width: 100%; }
                    to { width: 0%; }
                }
            `}</style>

            {/* ── Success Popup Modal ────────────────────────────────────────── */}
            {operationResult && (
                <div style={{
                    position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
                    backgroundColor: "rgba(0, 0, 0, 0.65)",
                    backdropFilter: "blur(6px)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    zIndex: 10000,
                    animation: "fadeIn 0.2s ease"
                }}>
                    <div style={{
                        background: "var(--bg-secondary)",
                        border: "1px solid var(--border-color)",
                        borderRadius: "12px",
                        padding: "24px",
                        width: "90%",
                        maxWidth: "420px",
                        boxShadow: "0 20px 25px -5px rgba(0,0,0,0.4), 0 10px 10px -5px rgba(0,0,0,0.4)",
                        color: "var(--text-primary)",
                        fontFamily: "var(--font-body)",
                        animation: "scaleIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)"
                    }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "18px" }}>
                            <div style={{
                                width: "32px", height: "32px", borderRadius: "50%",
                                background: operationResult.already_exists
                                    ? "linear-gradient(135deg, #3B82F6, #1D4ED8)"
                                    : "linear-gradient(135deg, #10B981, #059669)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                color: "#fff", fontSize: "1rem", fontWeight: "bold"
                            }}>
                                {operationResult.already_exists ? "i" : "✓"}
                            </div>
                            <h3 style={{
                                margin: 0, fontSize: "1.15rem", fontWeight: "700",
                                fontFamily: "var(--font-display)", color: "var(--text-primary)"
                            }}>
                                {operationResult.title}
                            </h3>
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "20px" }}>
                            {operationResult.type === "candles" && (
                                <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--border-color)", paddingBottom: "6px" }}>
                                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Status</span>
                                    <span style={{
                                        fontWeight: "700",
                                        fontSize: "0.75rem",
                                        color: operationResult.already_exists ? "#3B82F6" : "#10B981",
                                        background: operationResult.already_exists ? "rgba(59, 130, 246, 0.15)" : "rgba(16, 185, 129, 0.15)",
                                        padding: "2px 8px",
                                        borderRadius: "4px",
                                        border: operationResult.already_exists ? "1px solid rgba(59, 130, 246, 0.3)" : "1px solid rgba(16, 185, 129, 0.3)"
                                    }}>
                                        {operationResult.already_exists ? "Already Present (Bypassed API)" : "Newly Fetched & Stored"}
                                    </span>
                                </div>
                            )}
                            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--border-color)", paddingBottom: "6px" }}>
                                <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Symbol</span>
                                <span style={{ fontWeight: "600", fontSize: "0.8rem", color: "var(--accent-blue)" }}>{operationResult.symbol}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--border-color)", paddingBottom: "6px" }}>
                                <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Timeframe</span>
                                <span style={{ fontWeight: "600", fontSize: "0.8rem" }}>{operationResult.timeframe}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--border-color)", paddingBottom: "6px" }}>
                                <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Rows Processed</span>
                                <span style={{ fontWeight: "700", fontSize: "0.8rem", color: "#10B981" }}>{Number(operationResult.rows).toLocaleString()}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--border-color)", paddingBottom: "6px" }}>
                                <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Date Range</span>
                                <span style={{ fontWeight: "600", fontSize: "0.8rem" }}>{operationResult.fromDate} to {operationResult.toDate}</span>
                            </div>
                            {operationResult.duration && (
                                <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed var(--border-color)", paddingBottom: "6px" }}>
                                    <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Requested Duration</span>
                                    <span style={{ fontWeight: "600", fontSize: "0.8rem" }}>{operationResult.duration}</span>
                                </div>
                            )}
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end" }}>
                            <button
                                onClick={() => setOperationResult(null)}
                                style={{
                                    background: "linear-gradient(135deg, var(--accent-blue), #1D4ED8)",
                                    color: "#fff",
                                    border: "none",
                                    borderRadius: "6px",
                                    padding: "8px 18px",
                                    fontSize: "0.8rem",
                                    fontWeight: "600",
                                    cursor: "pointer",
                                    transition: "all 0.15s ease",
                                    boxShadow: "var(--shadow-glow-blue)"
                                }}
                                onMouseEnter={(e) => {
                                    e.target.style.filter = "brightness(1.1)";
                                }}
                                onMouseLeave={(e) => {
                                    e.target.style.filter = "brightness(1)";
                                }}
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Toast ────────────────────────────────────────── */}
            {toast && (
                <div style={{
                    position: "fixed", bottom: 24, right: 24, zIndex: 9999,
                    background: "rgba(30, 41, 59, 0.85)",
                    backdropFilter: "blur(12px)",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                    borderRadius: "10px",
                    padding: "12px 18px",
                    color: "#fff",
                    boxShadow: "0 10px 25px -5px rgba(0,0,0,0.5), 0 8px 10px -6px rgba(0,0,0,0.5), inset 0 1px 0 0 rgba(255,255,255,0.1)",
                    display: "flex", alignItems: "center", gap: "12px",
                    minWidth: "280px", maxWidth: "360px",
                    animation: "toastSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                    overflow: "hidden"
                }}>
                    {/* Icon */}
                    {toast.type === "success" && (
                        <div style={{
                            width: "20px", height: "20px", borderRadius: "50%",
                            background: "rgba(16, 185, 129, 0.2)",
                            border: "1px solid rgba(16, 185, 129, 0.4)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: "#10B981", fontSize: "0.8rem", fontWeight: "bold", flexShrink: 0
                        }}>
                            ✓
                        </div>
                    )}
                    {toast.type === "error" && (
                        <div style={{
                            width: "20px", height: "20px", borderRadius: "50%",
                            background: "rgba(239, 68, 68, 0.2)",
                            border: "1px solid rgba(239, 68, 68, 0.4)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: "#EF4444", fontSize: "0.8rem", fontWeight: "bold", flexShrink: 0
                        }}>
                            ✕
                        </div>
                    )}
                    {toast.type === "loading" && (
                        <div style={{
                            width: "16px", height: "16px",
                            border: "2px solid rgba(255, 255, 255, 0.2)",
                            borderTop: "2px solid var(--accent-blue)",
                            borderRadius: "50%",
                            animation: "toastSpin 0.8s linear infinite", flexShrink: 0
                        }} />
                    )}
                    {toast.type === "info" && (
                        <div style={{
                            width: "20px", height: "20px", borderRadius: "50%",
                            background: "rgba(59, 130, 246, 0.2)",
                            border: "1px solid rgba(59, 130, 246, 0.4)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: "#3B82F6", fontSize: "0.8rem", fontWeight: "bold", flexShrink: 0
                        }}>
                            i
                        </div>
                    )}

                    {/* Message */}
                    <div style={{
                        flex: 1, fontSize: "0.8rem", fontWeight: "500",
                        lineHeight: "1.4", fontFamily: "var(--font-body)", color: "#E2E8F0"
                    }}>
                        {toast.message}
                    </div>

                    {/* Close Button */}
                    <button
                        onClick={() => setToastState(null)}
                        style={{
                            background: "transparent", border: "none", color: "rgba(255, 255, 255, 0.4)",
                            fontSize: "0.8rem", cursor: "pointer", padding: "2px", display: "flex",
                            alignItems: "center", justifyContent: "center", transition: "color 0.15s ease",
                            fontFamily: "sans-serif"
                        }}
                        onMouseEnter={(e) => e.target.style.color = "#fff"}
                        onMouseLeave={(e) => e.target.style.color = "rgba(255, 255, 255, 0.4)"}
                    >
                        ✕
                    </button>

                    {/* Progress Bar (except for loading) */}
                    {toast.type !== "loading" && (
                        <div style={{
                            position: "absolute", bottom: 0, left: 0, height: "3px",
                            background: toast.type === "success" ? "#10B981" :
                                toast.type === "error" ? "#EF4444" :
                                    toast.type === "info" ? "#3B82F6" : "var(--accent-blue)",
                            width: "100%",
                            animation: "toastProgress 3s linear forwards"
                        }} />
                    )}
                </div>
            )}

            <div style={{
                maxWidth: "var(--max-width)",
                margin: "0 auto",
                padding: "24px var(--content-padding)",
                display: "flex",
                flexDirection: "column",
                gap: 20,
            }}>

                {/* ── ROW 1 — Greeting + Search + WS Status ────── */}
                <div style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 20,
                    flexWrap: "wrap",
                    width: "100%",
                }}>
                    {/* Greeting + avatar */}
                    <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                        <Avatar size={42} onClick={() => setProfileOpen(true)} />
                        <div>
                            <div style={{
                                fontSize: "0.72rem",
                                color: "var(--text-muted)",
                                fontFamily: "var(--font-body)",
                                fontWeight: 500,
                            }}>
                                {greeting},
                            </div>
                            <div
                                onClick={() => setProfileOpen(true)}
                                style={{
                                    fontSize: "1.3rem",
                                    fontWeight: 700,
                                    fontFamily: "var(--font-display)",
                                    color: "var(--text-primary)",
                                    letterSpacing: "-0.02em",
                                    lineHeight: 1.2,
                                    cursor: "pointer",
                                }}
                            >
                                {user} <span style={{ color: "var(--accent-blue)" }}>↗</span>
                            </div>
                        </div>
                    </div>

                    {/* Center Search Bar - Prominent & Highly Visible */}
                    <div style={{
                        flex: 1,
                        display: "flex",
                        justifyContent: "center",
                        maxWidth: 520,
                        minWidth: 280,
                    }}>
                        <SearchBar
                            search={search}
                            setSearch={setSearch}
                            showResults={showResults}
                            setShowResults={setShowResults}
                            debouncedSearch={debouncedSearch}
                            instruments={instruments}
                            watchlist={watchlist}
                            activeWatchlistCapLabel={activeWatchlistLabel}
                            toggleWatchlist={toggleWatchlist}
                            setSelectedSymbol={setSelectedSymbol}
                            setSelectedInstrument={setSelectedInstrument}
                            setSelectedInstruments={setSelectedInstruments}
                            getLtpForInstrument={getLtpForInstrument}
                            prices={prices}
                        />
                    </div>

                    {/* WS Status + Market Summary */}
                    <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        justifyContent: "flex-end",
                        flexShrink: 0,
                    }}>
                        <WebSocketStatus
                            isConnected={isConnected}
                            connectWebSocket={stableConnect}
                            disconnectWebSocket={stableDisconnect}
                        />
                        <MarketSummary marketSummary={marketSummary} asOf={asOf} />
                    </div>
                </div>

                {/* ── ROW 2 — Index Strip ──────────────────────── */}
                <IndexStrip prices={prices} indexData={indexData} />

                {/* ── ROW 3 — Main 3-column layout ─────────────── */}
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 360px",
                    gridTemplateRows: "auto",
                    gap: 16,
                }}>

                    {/* ── COL 1 — Watchlist ─────────────────────── */}
                    <Panel style={{ width: "100%", maxWidth: 520, justifySelf: "start" }}>
                        <SectionHeader
                            subtitle="Monitoring"
                            title="Watchlist"
                            action={
                                <span style={{
                                    fontSize: "0.7rem",
                                    fontFamily: "var(--font-mono)",
                                    color: "var(--text-muted)",
                                    background: "var(--bg-tertiary)",
                                    border: "1px solid var(--border-subtle)",
                                    borderRadius: 6,
                                    padding: "2px 8px",
                                }}>
                                    {activeWatchlist.length} shown / {watchlist.length} total
                                </span>
                            }
                        />
                        <div style={{
                            display: "flex",
                            gap: 6,
                            marginBottom: 10,
                            flexWrap: "wrap",
                        }}>
                            {WATCHLIST_CAP_OPTIONS.map((capItem) => {
                                const isActive = activeWatchlistCap === capItem.key;
                                return (
                                    <button
                                        key={capItem.key}
                                        onClick={() => setActiveWatchlistCap(capItem.key)}
                                        style={{
                                            borderRadius: 999,
                                            border: `1px solid ${isActive ? "var(--accent-blue)" : "var(--border-color)"}`,
                                            background: isActive ? "rgba(59,130,246,0.15)" : "var(--bg-secondary)",
                                            color: isActive ? "var(--accent-blue)" : "var(--text-muted)",
                                            fontSize: "0.68rem",
                                            fontFamily: "var(--font-body)",
                                            fontWeight: 600,
                                            padding: "5px 9px",
                                            cursor: "pointer",
                                        }}
                                        title={`Show ${capItem.label} list`}
                                    >
                                        {capItem.label} ({watchlistCountByCap[capItem.key] || 0})
                                    </button>
                                );
                            })}
                        </div>
                        {activeWatchlist.length === 0 ? (
                            <div style={{
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                justifyContent: "center",
                                minHeight: 120,
                                gap: 8,
                                border: "1px dashed var(--border-subtle)",
                                borderRadius: 10,
                                color: "var(--text-muted)",
                                fontSize: "0.78rem",
                                fontFamily: "var(--font-body)",
                            }}>
                                <span style={{ fontSize: "1.4rem" }}>☆</span>
                                No symbols in {activeWatchlistLabel}
                            </div>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                {activeWatchlist.map((w) => {
                                    const sym = w.symbol?.toUpperCase();
                                    const live = prices?.[sym] || {};
                                    const ltp = live.ltp;
                                    const pct = live.percent ?? 0;
                                    const isUp = (live.change ?? 0) >= 0;
                                    const hasP = typeof ltp === "number";
                                    const isSel = selectedSymbol === sym;
                                    return (
                                        <div
                                            key={sym}
                                            onClick={() => { setSelectedSymbol(sym); setSelectedInstrument(w); }}
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "space-between",
                                                padding: "9px 11px",
                                                borderRadius: 10,
                                                cursor: "pointer",
                                                background: isSel
                                                    ? "linear-gradient(135deg, rgba(59,130,246,0.18), rgba(59,130,246,0.08))"
                                                    : "var(--bg-secondary)",
                                                border: `1px solid ${isSel ? "var(--accent-blue)" : "var(--border-color)"}`,
                                                boxShadow: isSel
                                                    ? "0 0 0 1px rgba(59,130,246,0.2), var(--shadow-card)"
                                                    : "var(--shadow-card)",
                                                transition: "all 0.12s ease",
                                                gap: 10,
                                            }}
                                            onMouseEnter={e => {
                                                if (!isSel) {
                                                    e.currentTarget.style.background = "var(--bg-tertiary)";
                                                    e.currentTarget.style.borderColor = "var(--accent-blue)";
                                                }
                                            }}
                                            onMouseLeave={e => {
                                                if (!isSel) {
                                                    e.currentTarget.style.background = "var(--bg-secondary)";
                                                    e.currentTarget.style.border = "1px solid var(--border-color)";
                                                }
                                            }}
                                        >
                                            {/* Logo + symbol + exchange */}
                                            <StockLogo symbol={sym} size={30} borderRadius={7} />
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ fontSize: "0.82rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                                    {sym}
                                                </div>
                                                <div style={{ fontSize: "0.62rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                                                    {w.exchange || w.segment || ""}
                                                </div>
                                            </div>

                                            {/* Price */}
                                            <div style={{ textAlign: "right", flexShrink: 0, minWidth: 92 }}>
                                                <div style={{ fontSize: "0.82rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: hasP ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)" }}>
                                                    {hasP ? `₹${ltp.toLocaleString("en-IN")}` : "--"}
                                                </div>
                                                <div style={{ fontSize: "0.62rem", fontFamily: "var(--font-mono)", color: hasP ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)" }}>
                                                    {hasP ? `${isUp ? "▲" : "▼"} ${Math.abs(pct).toFixed(2)}%` : "--"}
                                                </div>
                                            </div>

                                            {/* Remove button */}
                                            <button
                                                onClick={e => {
                                                    e.stopPropagation();
                                                    toggleWatchlist(w);
                                                    // If this was the selected symbol, clear it
                                                    if (selectedSymbol === sym) {
                                                        setSelectedSymbol("");
                                                        setSelectedInstrument(null);
                                                    }
                                                }}
                                                title="Remove from watchlist"
                                                style={{
                                                    width: 26, height: 26,
                                                    borderRadius: 6,
                                                    border: "1px solid var(--border-color)",
                                                    background: "var(--bg-secondary)",
                                                    color: "var(--text-muted)",
                                                    cursor: "pointer",
                                                    fontSize: "0.65rem",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "center",
                                                    flexShrink: 0,
                                                    transition: "all 0.12s ease",
                                                }}
                                                onMouseEnter={e => {
                                                    e.currentTarget.style.background = "rgba(255,82,82,0.12)";
                                                    e.currentTarget.style.borderColor = "var(--accent-down)";
                                                    e.currentTarget.style.color = "var(--accent-down)";
                                                }}
                                                onMouseLeave={e => {
                                                    e.currentTarget.style.background = "var(--bg-secondary)";
                                                    e.currentTarget.style.borderColor = "var(--border-color)";
                                                    e.currentTarget.style.color = "var(--text-muted)";
                                                }}
                                            >
                                                ✕
                                            </button>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </Panel>

                    {/* ── COL 2 — Active Instruments ───────────── */}
                    <Panel style={{ width: "100%", maxWidth: 520, justifySelf: "start" }}>
                        <SectionHeader
                            subtitle="Working List"
                            title="Instruments"
                            action={
                                <span style={{
                                    fontSize: "0.7rem",
                                    fontFamily: "var(--font-mono)",
                                    color: "var(--text-muted)",
                                    background: "var(--bg-tertiary)",
                                    border: "1px solid var(--border-subtle)",
                                    borderRadius: 6,
                                    padding: "2px 8px",
                                }}>
                                    {selectedInstruments.length} added
                                </span>
                            }
                        />
                        <SelectedInstruments
                            selectedInstruments={selectedInstruments}
                            prices={prices}
                            selectedSymbol={selectedSymbol}
                            activeSubscriptions={activeSubscriptions}
                            normalizeKey={normalizeKey}
                            setSelectedSymbol={setSelectedSymbol}
                            setSelectedInstrument={setSelectedInstrument}
                            setSelectedInstruments={setSelectedInstruments}
                            subscribeToStock={subscribeToStock}
                        />
                    </Panel>

                    {/* ── COL 3 — Tools Panel ───────────────────── */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

                        {/* Tab switcher */}
                        <div style={{
                            display: "flex",
                            background: "var(--bg-secondary)",
                            border: "1px solid var(--border-color)",
                            borderRadius: "var(--card-radius)",
                            padding: 4, gap: 4,
                        }}>
                            {[
                                { key: "tools", label: "Data Tools" },
                                { key: "selected", label: "LTP Monitor" },
                            ].map(({ key, label }) => (
                                <button
                                    key={key}
                                    onClick={() => setActivePanel(key)}
                                    style={{
                                        flex: 1,
                                        padding: "7px 0",
                                        borderRadius: 8,
                                        border: "none",
                                        cursor: "pointer",
                                        fontFamily: "var(--font-body)",
                                        fontWeight: 600,
                                        fontSize: "0.78rem",
                                        transition: "all 0.15s ease",
                                        background: activePanel === key ? "var(--accent-blue)" : "transparent",
                                        color: activePanel === key ? "#fff" : "var(--text-muted)",
                                        boxShadow: activePanel === key ? "var(--shadow-glow-blue)" : "none",
                                    }}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>

                        {/* Tools Panel */}
                        {activePanel === "tools" && (
                            <ToolsPanel
                                selectedSymbol={selectedSymbol}
                                setSelectedSymbol={setSelectedSymbol}
                                startDate={startDate}
                                endDate={endDate}
                                setStartDate={setStartDate}
                                setEndDate={setEndDate}
                                histStart={histStart}
                                histEnd={histEnd}
                                setHistStart={setHistStart}
                                setHistEnd={setHistEnd}
                                timeframe={timeframe}
                                setTimeframe={setTimeframe}
                                timeframes={timeframes}
                                years={years}
                                setYears={setYears}
                                isApplyingIndicators={isApplyingIndicators}
                                runBulkFetch={runBulkFetch}
                                applyIndicators={applyIndicators}
                                fetchHistoricalCandles={fetchHistoricalCandles}
                                downloadExcel={downloadExcel}
                                force={force}
                                setForce={setForce}
                            />
                        )}

                        {/* LTP Monitor */}
                        {activePanel === "selected" && (
                            <Panel style={{ padding: "16px" }}>
                                <SectionHeader subtitle="Live Prices" title="LTP Monitor" />
                                {selectedInstruments.length === 0 ? (
                                    <div style={{
                                        textAlign: "center",
                                        padding: "24px 0",
                                        color: "var(--text-muted)",
                                        fontSize: "0.78rem",
                                        fontFamily: "var(--font-body)",
                                    }}>
                                        Add instruments from search
                                    </div>
                                ) : (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                        {selectedInstruments.map((item) => {
                                            const sym = (item.symbol || "").toUpperCase();
                                            const key = normalizeKey(item);
                                            const live = prices?.[key] || {};
                                            const ltp = live.ltp;
                                            const pct = live.percent ?? 0;
                                            const isUp = (live.change ?? 0) >= 0;
                                            const hasP = typeof ltp === "number";
                                            const isRunning = !!activeSubscriptions[key];
                                            const canShowLive = isRunning && hasP;

                                            return (
                                                <div key={key} style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "space-between",
                                                    padding: "10px 12px",
                                                    borderRadius: 8,
                                                    background: "var(--bg-tertiary)",
                                                    border: `1px solid ${isRunning ? "rgba(0,230,118,0.3)" : "var(--border-subtle)"}`,
                                                }}>
                                                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                                        <StockLogo symbol={sym} size={28} borderRadius={6} />
                                                        <div>
                                                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                                                {isRunning && (
                                                                    <span style={{
                                                                        width: 6, height: 6, borderRadius: "50%",
                                                                        background: "var(--accent-up)",
                                                                        boxShadow: "0 0 6px var(--accent-up)",
                                                                        animation: "ltsPulse 2s infinite",
                                                                        display: "inline-block",
                                                                    }} />
                                                                )}
                                                                <span style={{ fontSize: "0.82rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "var(--text-primary)" }}>
                                                                    {sym}
                                                                </span>
                                                            </div>
                                                            <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
                                                                {item.exchange || ""}
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div style={{ textAlign: "right" }}>
                                                        <div style={{
                                                            fontSize: "0.9rem",
                                                            fontWeight: 700,
                                                            fontFamily: "var(--font-mono)",
                                                            color: canShowLive ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)",
                                                        }}>
                                                            {canShowLive ? `₹${ltp.toLocaleString("en-IN")}` : "--"}
                                                        </div>
                                                        <div style={{
                                                            fontSize: "0.65rem",
                                                            fontFamily: "var(--font-mono)",
                                                            color: canShowLive ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)",
                                                        }}>
                                                            {canShowLive ? `${isUp ? "+" : ""}${pct.toFixed(2)}%` : "--"}
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </Panel>
                        )}
                    </div>
                </div>
            </div>

            <style>{`
                @keyframes slideIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to   { opacity: 1; transform: translateY(0); }
                }
                @keyframes ltsPulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50%      { opacity: 0.5; transform: scale(1.4); }
                }
            `}</style>

            {/* ── Profile drawer ───────────────────────────────── */}
            <ProfileDrawer
                open={profileOpen}
                onClose={() => setProfileOpen(false)}
            />
        </div>
    );
}
