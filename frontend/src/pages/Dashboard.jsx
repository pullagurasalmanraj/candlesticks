// src/pages/Dashboard.jsx
import React, { useState, useEffect, useMemo, useCallback } from "react";
import "react-datepicker/dist/react-datepicker.css";
import { useTheme } from "../context/ThemeContext";
import SkeletonLoader from "../components/SkeletonLoader";

import { INDEX_DEFAULTS, INDEX_NAME_TO_SYMBOL } from "../context/indexes";
import { normalizeKey } from "../utils/instrumentUtils";
import { getLtpForInstrument } from "../utils/priceUtils";
import { formatYMD, startOfDay } from "../utils/dateUtils";
import {
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
import TradingMotivationBanner from "../components/TradingMotivationBanner";
import MarketSummary from "../components/MarketSummary";
import IndexStrip from "../components/IndexStrip";
import LiveTickCard from "../components/LiveTickCard";
import LiveHeatmap from "../components/LiveHeatmap";
import DataToolsDrawer from "../components/DataToolsDrawer";
import ScreenerMetricsCard from "../components/ScreenerMetricsCard";
import MarketBreadthBarometer from "../components/MarketBreadthBarometer";
import ProfileDrawer, { Avatar } from "../components/ProfileDrawer";
import StockLogo from "../components/StockLogo";

import useInstrumentSearch from "../hooks/useInstrumentSearch";
import useWebSocketPrices from "../hooks/useWebSocketPrices.js";
import { fetchTimeframes } from "../services/timeframeService";
import { fetchHistoricalCandlesAPI } from "../services/candleService";
import {
    subscribeSymbol,
    subscribeInstruments,
    unsubscribeAllInstruments,
    unsubscribeInstrument
} from "../services/subscriptionService";
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

    // ── Primary State ────────────────────────────────────────────
    const [selectedInstruments, setSelectedInstruments] = useState(() => readStoredArray("selectedInstruments"));
    const [isApplyingIndicators, setIsApplyingIndicators] = useState(false);
    const [watchlistsByCap, setWatchlistsByCap] = useState(() => readStoredWatchlistsByCap());
    const [activeWatchlistCap, setActiveWatchlistCap] = useState(() => readPreferredWatchlistCap());
    const [selectedSymbol, setSelectedSymbol] = useState("");
    const [selectedInstrument, setSelectedInstrument] = useState(null);
    const [activeSubscriptions, setActiveSubscriptions] = useState(() => readStoredObject("activeSubscriptions"));

    // ── View & Layout State ──────────────────────────────────────
    const [viewMode, setViewMode] = useState("command_center"); // "command_center" | "heatmap" | "workbench"
    const [isToolsOpen, setIsToolsOpen] = useState(false);
    const [watchlistTab, setWatchlistTab] = useState("auto"); // "auto" | "watchlist" | "barometer"
    const [sortBy, setSortBy] = useState("default"); // "default" | "gainers" | "losers" | "symbol" | "price" | "subscribed"
    const [filterCategory, setFilterCategory] = useState("all"); // "all" | "gainers" | "losers" | "subscribed"
    const [fetchedLtpMap, setFetchedLtpMap] = useState({});

    const handleFundamentalsLoaded = useCallback((data) => {
        if (data && typeof data.currentPrice === "number" && selectedSymbol) {
            const cleanSym = String(selectedSymbol || "").split("|").pop().replace(/^(NSE_EQ|NSE_INDEX|BSE_EQ|BSE_INDEX)/, "").replace(/[^A-Z0-9]/g, "");
            setFetchedLtpMap(prev => ({ ...prev, [cleanSym]: data.currentPrice }));
        }
    }, [selectedSymbol]);

    // ── Data Tools State ─────────────────────────────────────────
    const [startDate, setStartDate] = useState(null);
    const [endDate, setEndDate] = useState(null);
    const [timeframes, setTimeframes] = useState([]);
    const [timeframe, setTimeframe] = useState("");
    const [histStart, setHistStart] = useState(null);
    const [histEnd, setHistEnd] = useState(null);
    const [isFetchingHistory, setIsFetchingHistory] = useState(false);
    const [years, setYears] = useState("");
    const [force, setForce] = useState(false);

    // ── Summary & Modal State ────────────────────────────────────
    const [indexData, setIndexData] = useState({});
    const [marketSummary, setMarketSummary] = useState(null);
    const [asOf, setAsOf] = useState(null);
    const [toast, setToastState] = useState(null);
    const [profileOpen, setProfileOpen] = useState(false);
    const [operationResult, setOperationResult] = useState(null);

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

    // ── Handlers ────────────────────────────────────────────────
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
    }, [activeSubscriptions, setToast]);

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

    const handleAddPresetSymbols = useCallback((symbolsList) => {
        if (!Array.isArray(symbolsList) || symbolsList.length === 0) return;

        const newInstruments = [];
        symbolsList.forEach((symName) => {
            const clean = symName.trim().toUpperCase();
            const inst = instruments.find(i => (i.symbol || i.trading_symbol || "").toUpperCase() === clean) || {
                symbol: clean,
                trading_symbol: clean,
                instrument_key: `NSE_EQ|${clean}`,
                name: clean,
            };
            newInstruments.push(inst);
        });

        setWatchlistsByCap((prevRaw) => {
            const prev = ensureWatchlistsShape(prevRaw);
            const next = { ...prev };
            const currentCapList = [...(next[activeWatchlistCap] || [])];

            newInstruments.forEach((inst) => {
                const s = normalizeSymbol(inst.symbol);
                if (!currentCapList.some(item => normalizeSymbol(item.symbol) === s)) {
                    currentCapList.push({ ...inst, symbol: s, cap: activeWatchlistCap });
                }
            });

            next[activeWatchlistCap] = currentCapList;
            return next;
        });

        setSelectedInstruments((prev) => {
            const existingKeys = new Set(prev.map(i => (i.symbol || i.trading_symbol || "").toUpperCase()));
            const toAdd = newInstruments.filter(i => !existingKeys.has((i.symbol || i.trading_symbol || "").toUpperCase()));
            return [...prev, ...toAdd];
        });

        setToast(`⚡ Added ${newInstruments.length} symbols to ${activeWatchlistLabel}`);
    }, [instruments, activeWatchlistCap, activeWatchlistLabel, setToast]);

    // ── Batch Action Handlers ────────────────────────────────────
    const streamAllWorkingList = useCallback(async () => {
        const keys = selectedInstruments.map((inst) => inst.instrument_key?.trim()).filter(Boolean);
        if (keys.length === 0) return setToast("No instruments in working list.");
        try {
            setToast("Subscribing to all working list instruments...");
            await subscribeInstruments(keys);
            const next = { ...activeSubscriptions };
            keys.forEach((k) => { next[k] = true; });
            setActiveSubscriptions(next);
            setToast(`Streaming ${keys.length} instruments`);
        } catch {
            setToast("Failed to subscribe all instruments.");
        }
    }, [selectedInstruments, activeSubscriptions, setToast]);

    const pauseAllStreams = useCallback(async () => {
        try {
            setToast("Pausing all live streams...");
            await unsubscribeAllInstruments();
            setActiveSubscriptions({});
            setToast("All live streams paused.");
        } catch {
            setToast("Failed to pause streams.");
        }
    }, [setToast]);

    const handleOpenToolsForSymbol = useCallback((sym) => {
        if (sym) {
            setSelectedSymbol(sym);
            const found = selectedInstruments.find(i => (i.symbol || "").toUpperCase() === sym) || watchlist.find(i => (i.symbol || "").toUpperCase() === sym);
            if (found) setSelectedInstrument(found);
        }
        setIsToolsOpen(true);
    }, [selectedInstruments, watchlist]);

    // ── Process Dynamic Sorting & Filtering ──────────────────────
    const processList = useCallback((list) => {
        let result = [...list];

        if (filterCategory === "gainers") {
            result = result.filter(item => {
                const key = normalizeKey(item);
                const p = prices[key] || prices[(item.symbol || "").toUpperCase()];
                return p && (p.percent ?? 0) > 0;
            });
        } else if (filterCategory === "losers") {
            result = result.filter(item => {
                const key = normalizeKey(item);
                const p = prices[key] || prices[(item.symbol || "").toUpperCase()];
                return p && (p.percent ?? 0) < 0;
            });
        } else if (filterCategory === "subscribed") {
            result = result.filter(item => {
                const key = normalizeKey(item);
                return !!activeSubscriptions[key];
            });
        }

        result.sort((a, b) => {
            const keyA = normalizeKey(a);
            const keyB = normalizeKey(b);
            const pA = prices[keyA] || prices[(a.symbol || "").toUpperCase()] || {};
            const pB = prices[keyB] || prices[(b.symbol || "").toUpperCase()] || {};

            if (sortBy === "gainers") return (pB.percent ?? -999) - (pA.percent ?? -999);
            if (sortBy === "losers") return (pA.percent ?? 999) - (pB.percent ?? 999);
            if (sortBy === "price") return (pB.ltp ?? 0) - (pA.ltp ?? 0);
            if (sortBy === "symbol") return (a.symbol || "").localeCompare(b.symbol || "");
            if (sortBy === "subscribed") return (activeSubscriptions[keyB] ? 1 : 0) - (activeSubscriptions[keyA] ? 1 : 0);
            return 0;
        });

        return result;
    }, [filterCategory, sortBy, prices, activeSubscriptions]);

    const filteredWorkingList = useMemo(() => processList(selectedInstruments), [processList, selectedInstruments]);
    const filteredWatchlist = useMemo(() => processList(activeWatchlist), [processList, activeWatchlist]);

    // Combine unique items for Heatmap
    const heatmapItems = useMemo(() => {
        const map = new Map();
        selectedInstruments.forEach(item => {
            const sym = (item.symbol || "").toUpperCase();
            if (sym) map.set(sym, item);
        });
        watchlist.forEach(item => {
            const sym = (item.symbol || "").toUpperCase();
            if (sym && !map.has(sym)) map.set(sym, item);
        });
        return processList(Array.from(map.values()));
    }, [selectedInstruments, watchlist, processList]);

    // ── Data Tools API Calls ─────────────────────────────────────
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
    const hour = new Date().getHours();
    const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

    return (
        <div style={{
            minHeight: "calc(100vh - var(--navbar-height))",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
        }}>
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
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end" }}>
                            <button
                                onClick={() => setOperationResult(null)}
                                style={{
                                    background: "linear-gradient(135deg, var(--accent-blue), #1D4ED8)",
                                    color: "#fff", border: "none", borderRadius: "6px",
                                    padding: "8px 18px", fontSize: "0.8rem", fontWeight: "600",
                                    cursor: "pointer", boxShadow: "var(--shadow-glow-blue)"
                                }}
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Toast Notification ─────────────────────────────────── */}
            {toast && (
                <div style={{
                    position: "fixed", bottom: 24, right: 24, zIndex: 9999,
                    background: "rgba(30, 41, 59, 0.9)", backdropFilter: "blur(12px)",
                    border: "1px solid rgba(255, 255, 255, 0.1)", borderRadius: "10px",
                    padding: "12px 18px", color: "#fff",
                    boxShadow: "0 10px 25px -5px rgba(0,0,0,0.5)",
                    display: "flex", alignItems: "center", gap: "12px",
                    minWidth: "280px", maxWidth: "360px"
                }}>
                    <div style={{ flex: 1, fontSize: "0.8rem", fontWeight: "500" }}>{toast.message}</div>
                    <button onClick={() => setToastState(null)} style={{ background: "transparent", border: "none", color: "#888", cursor: "pointer" }}>✕</button>
                </div>
            )}

            {/* ── Floating Data Tools Drawer ───────────────────────────── */}
            <DataToolsDrawer
                isOpen={isToolsOpen}
                onClose={() => setIsToolsOpen(false)}
                selectedSymbol={selectedSymbol}
                setSelectedSymbol={setSelectedSymbol}
                selectedInstrument={selectedInstrument}
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

            <div style={{
                maxWidth: "var(--max-width)",
                margin: "0 auto",
                padding: "24px var(--content-padding)",
                display: "flex",
                flexDirection: "column",
                gap: 20,
            }}>
                {/* ── HEADER TOOLBAR — Greeting + Search + View Switcher + Data Tools Trigger ── */}
                <div style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 16,
                    flexWrap: "wrap",
                    width: "100%",
                }}>
                    {/* Greeting & Avatar */}
                    <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                        <Avatar size={42} onClick={() => setProfileOpen(true)} />
                        <div>
                            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 500 }}>
                                {greeting},
                            </div>
                            <div
                                onClick={() => setProfileOpen(true)}
                                style={{
                                    fontSize: "1.25rem", fontWeight: 700, fontFamily: "var(--font-display)",
                                    color: "var(--text-primary)", cursor: "pointer",
                                }}
                            >
                                {user} <span style={{ color: "var(--accent-blue)" }}>↗</span>
                            </div>
                        </div>
                    </div>

                    {/* Search Bar */}
                    <div style={{ flex: 1, display: "flex", justifyContent: "center", maxWidth: 480, minWidth: 260 }}>
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

                    {/* View Switcher + Data Tools Trigger + WS Status */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>

                        {/* View Switcher Tabs */}
                        <div style={{
                            display: "flex", background: "var(--bg-secondary)",
                            border: "1px solid var(--border-color)", borderRadius: 8, padding: 3, gap: 3
                        }}>
                            {[
                                { id: "command_center", label: "📊 Stream Terminal" },
                                { id: "heatmap", label: "🔥 Heatmap Matrix" },
                                { id: "workbench", label: "🎯 Analytical Focus" },
                            ].map(tab => (
                                <button
                                    key={tab.id}
                                    onClick={() => setViewMode(tab.id)}
                                    style={{
                                        border: "none", borderRadius: 6, padding: "6px 12px",
                                        fontSize: "0.74rem", fontWeight: 600, cursor: "pointer",
                                        background: viewMode === tab.id ? "var(--accent-blue)" : "transparent",
                                        color: viewMode === tab.id ? "#fff" : "var(--text-muted)",
                                        transition: "all 0.15s ease",
                                    }}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>

                        {/* ⚡ Data Tools Floating Drawer Button */}
                        <button
                            type="button"
                            onClick={() => setIsToolsOpen(true)}
                            style={{
                                border: "1px solid var(--accent-blue)",
                                borderRadius: 8,
                                background: "rgba(59,130,246,0.15)",
                                color: "var(--accent-blue)",
                                padding: "7px 14px",
                                fontSize: "0.78rem",
                                fontWeight: 700,
                                fontFamily: "var(--font-body)",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: 6,
                                boxShadow: "var(--shadow-glow-blue)",
                                transition: "all 0.15s ease",
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.transform = "scale(1.04)"}
                            onMouseLeave={(e) => e.currentTarget.style.transform = "scale(1)"}
                        >
                            <span>⚡ Data Tools</span>
                            {selectedSymbol && (
                                <span style={{
                                    fontSize: "0.62rem",
                                    background: "var(--accent-blue)",
                                    color: "#fff",
                                    borderRadius: 4,
                                    padding: "1px 5px"
                                }}>
                                    {selectedSymbol}
                                </span>
                            )}
                        </button>

                        <TradingMotivationBanner />
                        <MarketSummary marketSummary={marketSummary} asOf={asOf} />
                    </div>
                </div>

                {/* ── ROW 2 — Index Strip ──────────────────────── */}
                <IndexStrip prices={prices} indexData={indexData} />

                {/* ── CONTROL BAR — Filters, Sorting & Batch Actions ─────── */}
                <div style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    flexWrap: "wrap",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--card-radius)",
                    padding: "10px 16px",
                }}>
                    {/* Filter Category Pills */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>
                            Filter:
                        </span>
                        {[
                            { id: "all", label: "All Stocks" },
                            { id: "gainers", label: "🟢 Gainers" },
                            { id: "losers", label: "🔴 Losers" },
                            { id: "subscribed", label: "⚡ Streaming" },
                        ].map(f => (
                            <button
                                key={f.id}
                                onClick={() => setFilterCategory(f.id)}
                                style={{
                                    borderRadius: 20,
                                    border: `1px solid ${filterCategory === f.id ? "var(--accent-blue)" : "var(--border-subtle)"}`,
                                    background: filterCategory === f.id ? "rgba(59,130,246,0.18)" : "transparent",
                                    color: filterCategory === f.id ? "var(--accent-blue)" : "var(--text-muted)",
                                    fontSize: "0.7rem", fontWeight: 600, padding: "3px 10px", cursor: "pointer",
                                }}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>

                    {/* Sorting Dropdown & Batch Stream Controls */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 700 }}>Sort By:</span>
                            <select
                                value={sortBy}
                                onChange={(e) => setSortBy(e.target.value)}
                                style={{
                                    background: "var(--bg-tertiary)",
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 6,
                                    color: "var(--text-primary)",
                                    fontSize: "0.74rem",
                                    padding: "4px 8px",
                                    outline: "none",
                                }}
                            >
                                <option value="default">Default Order</option>
                                <option value="gainers">Top Gainers (% High to Low)</option>
                                <option value="losers">Top Losers (% Low to High)</option>
                                <option value="symbol">Symbol Name (A-Z)</option>
                                <option value="price">Price (LTP High to Low)</option>
                                <option value="subscribed">Streaming Active First</option>
                            </select>
                        </div>

                        {/* Batch Action Buttons */}
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <button
                                type="button"
                                onClick={streamAllWorkingList}
                                title="Subscribe WSS ticks for all working list stocks"
                                style={{
                                    border: "1px solid rgba(0,230,118,0.4)",
                                    background: "rgba(0,230,118,0.15)",
                                    color: "var(--accent-up)",
                                    borderRadius: 6, padding: "4px 10px",
                                    fontSize: "0.7rem", fontWeight: 700, cursor: "pointer",
                                }}
                            >
                                ▶ Stream All
                            </button>

                            <button
                                type="button"
                                onClick={pauseAllStreams}
                                title="Pause all live WSS tick subscriptions"
                                style={{
                                    border: "1px solid rgba(255,82,82,0.4)",
                                    background: "rgba(255,82,82,0.15)",
                                    color: "var(--accent-down)",
                                    borderRadius: 6, padding: "4px 10px",
                                    fontSize: "0.7rem", fontWeight: 700, cursor: "pointer",
                                }}
                            >
                                ■ Pause All
                            </button>
                        </div>
                    </div>
                </div>

                {/* ── MAIN CONTENT GRID — Dynamic views occupy 100% of Grid ────────── */}

                {/* VIEW MODE 1: COMMAND CENTER (Default Split Live Stream Grid) */}
                {viewMode === "command_center" && (
                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 16,
                        width: "100%",
                    }}>
                        {/* COLUMN 1: Dynamic Watchlist Stream & Market Barometer */}
                        <Panel>
                            <SectionHeader
                                subtitle="Market Watchlist & Macro Cockpit"
                                title={watchlistTab === "barometer" ? "Market Breadth & Sector Barometer" : activeWatchlistLabel}
                                action={
                                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <div style={{
                                            display: "flex",
                                            background: "var(--bg-tertiary)",
                                            border: "1px solid var(--border-color)",
                                            borderRadius: 6,
                                            padding: 2,
                                            gap: 2,
                                        }}>
                                            <button
                                                type="button"
                                                onClick={() => setWatchlistTab("watchlist")}
                                                style={{
                                                    background: watchlistTab !== "barometer" ? "var(--accent-blue)" : "transparent",
                                                    color: watchlistTab !== "barometer" ? "#fff" : "var(--text-muted)",
                                                    border: "none",
                                                    borderRadius: 4,
                                                    padding: "3px 8px",
                                                    fontSize: "0.68rem",
                                                    fontWeight: 600,
                                                    cursor: "pointer",
                                                }}
                                            >
                                                📋 Watchlist ({watchlist.length})
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => setWatchlistTab("barometer")}
                                                style={{
                                                    background: watchlistTab === "barometer" ? "var(--accent-blue)" : "transparent",
                                                    color: watchlistTab === "barometer" ? "#fff" : "var(--text-muted)",
                                                    border: "none",
                                                    borderRadius: 4,
                                                    padding: "3px 8px",
                                                    fontSize: "0.68rem",
                                                    fontWeight: 600,
                                                    cursor: "pointer",
                                                }}
                                            >
                                                🧭 Market Barometer
                                            </button>
                                        </div>
                                    </div>
                                }
                            />

                            {/* If Barometer View is Active OR Watchlist is Empty */}
                            {(watchlistTab === "barometer" || (watchlistTab === "auto" && filteredWatchlist.length === 0)) ? (
                                <MarketBreadthBarometer
                                    onAddPreset={handleAddPresetSymbols}
                                    onSelectSymbol={handleOpenToolsForSymbol}
                                />
                            ) : (
                                <>
                                    {/* Market Cap Filter Pills */}
                                    <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
                                        {WATCHLIST_CAP_OPTIONS.map((capItem) => {
                                            const isActive = activeWatchlistCap === capItem.key;
                                            return (
                                                <button
                                                    key={capItem.key}
                                                    onClick={() => setActiveWatchlistCap(capItem.key)}
                                                    style={{
                                                        borderRadius: 999,
                                                        border: `1px solid ${isActive ? "var(--accent-blue)" : "var(--border-color)"}`,
                                                        background: isActive ? "rgba(59,130,246,0.18)" : "var(--bg-secondary)",
                                                        color: isActive ? "var(--accent-blue)" : "var(--text-muted)",
                                                        fontSize: "0.68rem", fontWeight: 600, padding: "4px 10px", cursor: "pointer",
                                                    }}
                                                >
                                                    {capItem.label} ({watchlistCountByCap[capItem.key] || 0})
                                                </button>
                                            );
                                        })}
                                    </div>

                                    {/* Watchlist Cards List */}
                                    {filteredWatchlist.length === 0 ? (
                                        <MarketBreadthBarometer
                                            onAddPreset={handleAddPresetSymbols}
                                            onSelectSymbol={handleOpenToolsForSymbol}
                                        />
                                    ) : (
                                        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                            {filteredWatchlist.map((w) => {
                                                const sym = (w.symbol || "").toUpperCase();
                                                const key = normalizeKey(w);
                                                return (
                                                    <LiveTickCard
                                                        key={key || sym}
                                                        item={w}
                                                        priceData={prices[key] || prices[sym]}
                                                        selectedSymbol={selectedSymbol}
                                                        activeSubscriptions={activeSubscriptions}
                                                        normalizeKey={normalizeKey}
                                                        setSelectedSymbol={setSelectedSymbol}
                                                        setSelectedInstrument={setSelectedInstrument}
                                                        subscribeToStock={subscribeToStock}
                                                        onOpenTools={handleOpenToolsForSymbol}
                                                        onRemove={(inst) => toggleWatchlist(inst)}
                                                    />
                                                );
                                            })}
                                        </div>
                                    )}
                                </>
                            )}
                        </Panel>

                        {/* COLUMN 2: Working List & Active Live Stream Cards */}
                        <Panel>
                            <SectionHeader
                                subtitle="Working Stream List"
                                title="Active Streaming Tickers"
                                action={
                                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                        <span style={{
                                            fontSize: "0.7rem", fontFamily: "var(--font-mono)",
                                            color: "var(--accent-up)", background: "rgba(0,230,118,0.12)",
                                            border: "1px solid rgba(0,230,118,0.3)", borderRadius: 6, padding: "2px 8px"
                                        }}>
                                            {Object.keys(activeSubscriptions).length} active WSS streams
                                        </span>
                                        {selectedInstruments.length > 0 && (
                                            <button
                                                type="button"
                                                onClick={() => setSelectedInstruments([])}
                                                style={{
                                                    background: "transparent", border: "none",
                                                    color: "var(--accent-down)", fontSize: "0.7rem", cursor: "pointer",
                                                    fontWeight: 600,
                                                }}
                                            >
                                                Clear All
                                            </button>
                                        )}
                                    </div>
                                }
                            />

                            {filteredWorkingList.length === 0 ? (
                                <div style={{
                                    display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                                    minHeight: 180, border: "1px dashed var(--border-subtle)", borderRadius: 10,
                                    color: "var(--text-muted)", fontSize: "0.8rem", textAlign: "center", gap: 8, padding: 20
                                }}>
                                    <div style={{ fontSize: "1.5rem" }}>🔍</div>
                                    <div>Use the search bar above to add stocks to your working list.</div>
                                </div>
                            ) : (
                                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                    {filteredWorkingList.map((item) => {
                                        const sym = (item.symbol || "").toUpperCase();
                                        const key = normalizeKey(item);
                                        return (
                                            <LiveTickCard
                                                key={key || sym}
                                                item={item}
                                                priceData={prices[key] || prices[sym]}
                                                selectedSymbol={selectedSymbol}
                                                activeSubscriptions={activeSubscriptions}
                                                normalizeKey={normalizeKey}
                                                setSelectedSymbol={setSelectedSymbol}
                                                setSelectedInstrument={setSelectedInstrument}
                                                subscribeToStock={subscribeToStock}
                                                onOpenTools={handleOpenToolsForSymbol}
                                                onRemove={(inst) => {
                                                    setSelectedInstruments(prev => prev.filter(p => normalizeKey(p) !== normalizeKey(inst)));
                                                }}
                                            />
                                        );
                                    })}
                                </div>
                            )}
                        </Panel>
                    </div>
                )}

                {/* VIEW MODE 2: HEATMAP MATRIX (Full-width dynamic visual grid) */}
                {viewMode === "heatmap" && (
                    <Panel>
                        <SectionHeader
                            subtitle="Visual Stream Matrix"
                            title="Live Performance Heatmap"
                            action={
                                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                                    {heatmapItems.length} symbols in matrix
                                </span>
                            }
                        />
                        <LiveHeatmap
                            items={heatmapItems}
                            prices={prices}
                            selectedSymbol={selectedSymbol}
                            activeSubscriptions={activeSubscriptions}
                            normalizeKey={normalizeKey}
                            setSelectedSymbol={setSelectedSymbol}
                            setSelectedInstrument={setSelectedInstrument}
                            onOpenTools={handleOpenToolsForSymbol}
                        />
                    </Panel>
                )}

                {/* VIEW MODE 3: ANALYTICAL WORKBENCH (Hero Stock Header + Vertical Screener Ratios + Quick Data Tools) */}
                {viewMode === "workbench" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                        <Panel>
                            <SectionHeader
                                subtitle="Analytical Focus"
                                title={selectedSymbol ? `${selectedSymbol} Analytical Focus` : "Select a Stock to Focus Analytics"}
                                action={
                                    selectedSymbol && (
                                        <button
                                            type="button"
                                            onClick={() => setIsToolsOpen(true)}
                                            style={{
                                                background: "linear-gradient(135deg, var(--accent-blue), #1D4ED8)",
                                                color: "#fff",
                                                border: "none", borderRadius: 8, padding: "8px 16px",
                                                fontSize: "0.8rem", fontWeight: 700, cursor: "pointer",
                                                boxShadow: "var(--shadow-glow-blue)",
                                                display: "flex", alignItems: "center", gap: 6,
                                            }}
                                        >
                                            <span>⚡ Data Tools Workbench</span>
                                        </button>
                                    )
                                }
                            />

                            {selectedSymbol ? (
                                <div style={{
                                    display: "grid",
                                    gridTemplateColumns: "1fr 340px",
                                    gap: 20,
                                    width: "100%",
                                }}>
                                    {/* Left Column: Hero Stock Header + Screener Vertical Fundamentals Stack */}
                                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

                                        {/* Hero Stock Header */}
                                        <div style={{
                                            display: "flex", alignItems: "center", justifyContent: "space-between",
                                            background: "linear-gradient(135deg, var(--bg-secondary), var(--bg-tertiary))",
                                            padding: "20px 24px", borderRadius: 14,
                                            border: "1px solid var(--border-color)",
                                            boxShadow: "var(--shadow-card)",
                                            gap: 16,
                                        }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                                                <StockLogo symbol={selectedSymbol} size={48} borderRadius={12} />
                                                <div>
                                                    <div style={{ fontSize: "1.6rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "var(--text-primary)", lineHeight: 1.1 }}>
                                                        {selectedSymbol}
                                                    </div>
                                                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 4 }}>
                                                        {selectedInstrument?.instrument_key || selectedSymbol} • NSE EQ
                                                    </div>
                                                </div>
                                            </div>

                                            <div style={{ textAlign: "right" }}>
                                                {(() => {
                                                    const key = selectedInstrument ? normalizeKey(selectedInstrument) : selectedSymbol;
                                                    const cleanSym = String(selectedSymbol || "").split("|").pop().replace(/^(NSE_EQ|NSE_INDEX|BSE_EQ|BSE_INDEX)/, "").replace(/[^A-Z0-9]/g, "");
                                                    const p = prices[key] || prices[selectedSymbol] || prices[cleanSym] || prices[`NSE_EQ:${cleanSym}`] || {};
                                                    const ltp = typeof p.ltp === "number" ? p.ltp : fetchedLtpMap[cleanSym];
                                                    const pct = p.percent ?? 0;
                                                    const isUp = (p.change ?? 0) >= 0;
                                                    const hasP = typeof ltp === "number";
                                                    return (
                                                        <div>
                                                            <div style={{
                                                                fontSize: "1.8rem", fontWeight: 700, fontFamily: "var(--font-mono)",
                                                                color: hasP ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)",
                                                                fontVariantNumeric: "tabular-nums", lineHeight: 1.1,
                                                            }}>
                                                                {hasP ? `₹${ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "Fetching LTP..."}
                                                            </div>
                                                            <div style={{
                                                                fontSize: "0.88rem", fontWeight: 700, fontFamily: "var(--font-mono)",
                                                                color: hasP ? (isUp ? "var(--accent-up)" : "var(--accent-down)") : "var(--text-muted)",
                                                                fontVariantNumeric: "tabular-nums", marginTop: 4,
                                                            }}>
                                                                {hasP ? `${isUp ? "▲ +" : "▼ "}${pct.toFixed(2)}%` : "Live Price Synced"}
                                                            </div>
                                                        </div>
                                                    );
                                                })()}
                                            </div>
                                        </div>

                                        {/* Screener.in Vertical Market Cap & Fundamentals Card */}
                                        <ScreenerMetricsCard
                                            symbol={selectedSymbol}
                                            instrument={selectedInstrument}
                                            priceData={prices[selectedInstrument ? normalizeKey(selectedInstrument) : selectedSymbol] || prices[selectedSymbol]}
                                            capCategory={activeWatchlistCap}
                                            onDataLoaded={handleFundamentalsLoaded}
                                        />
                                    </div>

                                    {/* Right Column: Analytics Controls & Quick Actions */}
                                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

                                        {/* WSS Live Stream Card */}
                                        <div style={{
                                            background: "var(--bg-tertiary)",
                                            border: "1px solid var(--border-color)",
                                            borderRadius: 12, padding: "18px",
                                            display: "flex", flexDirection: "column", gap: 12,
                                        }}>
                                            <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                                                ⚡ Live Tick Streaming
                                            </div>

                                            {(() => {
                                                const key = selectedInstrument ? normalizeKey(selectedInstrument) : selectedSymbol;
                                                const isRunning = !!activeSubscriptions[key];
                                                return (
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                                            <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>Stream Status:</span>
                                                            <span style={{
                                                                fontSize: "0.74rem", fontWeight: 700, fontFamily: "var(--font-mono)",
                                                                color: isRunning ? "var(--accent-up)" : "var(--text-muted)",
                                                                background: isRunning ? "rgba(0,230,118,0.15)" : "var(--bg-secondary)",
                                                                border: `1px solid ${isRunning ? "rgba(0,230,118,0.3)" : "var(--border-color)"}`,
                                                                borderRadius: 4, padding: "2px 8px"
                                                            }}>
                                                                {isRunning ? "● STREAMING LIVE" : "○ PAUSED"}
                                                            </span>
                                                        </div>

                                                        <button
                                                            type="button"
                                                            onClick={() => subscribeToStock(selectedInstrument || { symbol: selectedSymbol, instrument_key: selectedSymbol })}
                                                            style={{
                                                                width: "100%", padding: "10px", borderRadius: 8,
                                                                border: isRunning ? "1px solid rgba(255,82,82,0.4)" : "1px solid rgba(0,230,118,0.4)",
                                                                background: isRunning ? "rgba(255,82,82,0.15)" : "rgba(0,230,118,0.15)",
                                                                color: isRunning ? "var(--accent-down)" : "var(--accent-up)",
                                                                fontWeight: 700, fontSize: "0.8rem", cursor: "pointer",
                                                                transition: "all 0.15s ease",
                                                            }}
                                                        >
                                                            {isRunning ? "■ Pause WSS Live Stream" : "▶ Start WSS Live Stream"}
                                                        </button>
                                                    </div>
                                                );
                                            })()}
                                        </div>

                                        {/* Quick Data Tools Launcher Card */}
                                        <div style={{
                                            background: "var(--bg-tertiary)",
                                            border: "1px solid var(--border-color)",
                                            borderRadius: 12, padding: "18px",
                                            display: "flex", flexDirection: "column", gap: 12,
                                        }}>
                                            <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", color: "var(--text-muted)" }}>
                                                📊 Indicator & History Actions
                                            </div>

                                            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", lineHeight: 1.4, margin: 0 }}>
                                                Generate technical indicators, calculate signals, or download historical candles directly into DB.
                                            </p>

                                            <button
                                                type="button"
                                                onClick={() => setIsToolsOpen(true)}
                                                style={{
                                                    width: "100%", padding: "11px", borderRadius: 8,
                                                    border: "none", background: "var(--accent-blue)",
                                                    color: "#fff", fontWeight: 700, fontSize: "0.82rem", cursor: "pointer",
                                                    boxShadow: "var(--shadow-glow-blue)",
                                                    transition: "all 0.15s ease",
                                                }}
                                            >
                                                ⚡ Launch Data Tools Drawer
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div style={{
                                    padding: 60, textAlign: "center", color: "var(--text-muted)",
                                    border: "1px dashed var(--border-subtle)", borderRadius: 12,
                                    display: "flex", flexDirection: "column", alignItems: "center", gap: 10
                                }}>
                                    <div style={{ fontSize: "2rem" }}>🎯</div>
                                    <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                        No Stock Selected
                                    </div>
                                    <div style={{ fontSize: "0.8rem", maxWidth: 360 }}>
                                        Click any stock card from your Watchlist or Working Stream List above to view live Screener.in fundamentals and ratios.
                                    </div>
                                </div>
                            )}
                        </Panel>
                    </div>
                )}
            </div>

            {/* Profile Drawer */}
            <ProfileDrawer
                open={profileOpen}
                onClose={() => setProfileOpen(false)}
            />
        </div>
    );
}
