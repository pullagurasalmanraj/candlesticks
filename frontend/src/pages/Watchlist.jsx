import React, { useEffect, useMemo, useRef, useState } from "react";
import { getWebSocketUrl } from "../utils/websocketUrl";
import {
    DEFAULT_WATCHLIST_CAP,
    WATCHLIST_CAP_KEYS,
    WATCHLIST_CAP_OPTIONS,
    WATCHLIST_LEGACY_KEY,
    WATCHLIST_STORAGE_KEY,
    ensureWatchlistsShape,
    flattenWatchlistsByCap,
    getWatchlistCapLabel,
    readPreferredWatchlistCap,
    readStoredWatchlistsByCap,
    savePreferredWatchlistCap,
} from "../utils/watchlistUtils";

export default function Watchlist() {
    const [watchlistsByCap, setWatchlistsByCap] = useState(() => readStoredWatchlistsByCap());
    const [activeCap, setActiveCap] = useState(() => readPreferredWatchlistCap());
    const [prices, setPrices] = useState({});
    const [priceChange, setPriceChange] = useState({});

    const wsRef = useRef(null);
    const reconnectRef = useRef(null);
    const mountedRef = useRef(false);

    const allWatchlistItems = useMemo(
        () => flattenWatchlistsByCap(watchlistsByCap),
        [watchlistsByCap]
    );
    const activeWatchlistItems = watchlistsByCap[activeCap] || [];

    const watchlistCountByCap = useMemo(() => {
        const safe = ensureWatchlistsShape(watchlistsByCap);
        const counts = {};
        WATCHLIST_CAP_KEYS.forEach((cap) => {
            counts[cap] = safe[cap].length;
        });
        return counts;
    }, [watchlistsByCap]);

    useEffect(() => {
        try {
            localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(watchlistsByCap));
            localStorage.setItem(WATCHLIST_LEGACY_KEY, JSON.stringify(allWatchlistItems));
        } catch {
            // ignore storage write failures
        }
    }, [watchlistsByCap, allWatchlistItems]);
    useEffect(() => {
        savePreferredWatchlistCap(activeCap);
    }, [activeCap]);

    // WebSocket connection
    useEffect(() => {
        if (mountedRef.current) return;
        mountedRef.current = true;

        function connectWS() {
            if (wsRef.current) return;

            const ws = new WebSocket(getWebSocketUrl());
            wsRef.current = ws;

            ws.onopen = () => {
                const keys = allWatchlistItems
                    .map((x) => x.instrument_key)
                    .filter(Boolean);

                if (keys.length > 0) {
                    ws.send(JSON.stringify({ subscribe: keys }));
                }
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg?.data?.type === "market_info") return;

                    const feeds = msg?.data?.feeds;
                    if (!feeds) return;

                    const newPrices = {};
                    const newTrends = {};

                    Object.entries(feeds).forEach(([ik, feed]) => {
                        const ltpc = feed.fullFeed?.marketFF?.ltpc;
                        if (!ltpc) return;

                        const ltp = ltpc.ltp;
                        const prevClose = ltpc.cp;
                        const change = ltp - prevClose;
                        const percent = prevClose ? (change / prevClose) * 100 : 0;

                        const trend = change > 0 ? "up" : change < 0 ? "down" : "neutral";

                        newPrices[ik] = { ltp, change, percent };
                        newTrends[ik] = trend;
                    });

                    setPrices((prev) => ({ ...prev, ...newPrices }));
                    setPriceChange((prev) => ({ ...prev, ...newTrends }));
                } catch {
                    // ignore malformed events
                }
            };

            ws.onclose = () => {
                wsRef.current = null;
                reconnectRef.current = setTimeout(connectWS, 2000);
            };
        }

        connectWS();

        return () => {
            if (wsRef.current) wsRef.current.close();
            clearTimeout(reconnectRef.current);
        };
    }, []);

    // Resubscribe on watchlist change
    useEffect(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            const keys = allWatchlistItems
                .map((x) => x.instrument_key)
                .filter(Boolean);
            wsRef.current.send(JSON.stringify({ subscribe: keys }));
        }
    }, [allWatchlistItems]);

    const removeFromWatchlist = (symbol) => {
        const capItems = activeWatchlistItems;
        const removedItem = capItems.find((s) => s.symbol === symbol);

        setWatchlistsByCap((prevRaw) => {
            const prev = ensureWatchlistsShape(prevRaw);
            const next = {};

            WATCHLIST_CAP_KEYS.forEach((cap) => {
                next[cap] = [...prev[cap]];
            });

            next[activeCap] = next[activeCap].filter((s) => s.symbol !== symbol);
            return next;
        });

        if (removedItem && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(
                JSON.stringify({
                    unsubscribe: [removedItem.instrument_key],
                })
            );
        }
    };

    return (
        <div className="p-6 min-h-screen" style={{ background: "transparent", color: "var(--text-primary)" }}>
            <h2 className="text-3xl font-bold mb-6" style={{ color: "var(--accent-gold)" }}>
                My Watchlist
            </h2>

            <div className="flex flex-wrap gap-2 mb-5">
                {WATCHLIST_CAP_OPTIONS.map((capItem) => {
                    const isActive = activeCap === capItem.key;
                    return (
                        <button
                            key={capItem.key}
                            onClick={() => setActiveCap(capItem.key)}
                            className="px-3 py-1.5 rounded-full text-sm border transition"
                            style={{
                                borderColor: isActive ? "var(--accent-blue)" : "var(--border-color)",
                                background: isActive ? "var(--accent-blue-muted)" : "var(--bg-secondary)",
                                color: isActive ? "var(--accent-blue)" : "var(--text-secondary)",
                                boxShadow: isActive ? "var(--shadow-glow-blue)" : "none",
                            }}
                        >
                            {capItem.label} ({watchlistCountByCap[capItem.key] || 0})
                        </button>
                    );
                })}
            </div>

            {activeWatchlistItems.length === 0 ? (
                <p className="text-center mt-20" style={{ color: "var(--text-muted)" }}>
                    {getWatchlistCapLabel(activeCap)} list is empty.
                </p>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                    {activeWatchlistItems.map((inst) => {
                        const key = inst.instrument_key;
                        const info = prices[key] || {};

                        const ltp = info.ltp ?? "--";
                        const change = info.change ?? 0;
                        const percent = info.percent ?? 0;

                        const trend = priceChange[key];
                        const color = trend === "up"
                            ? "var(--accent-up)"
                            : trend === "down" ? "var(--accent-down)" : "var(--accent-blue)";

                        return (
                            <div
                                key={`${activeCap}-${inst.symbol}-${key}`}
                                className="relative p-4 border"
                                style={{
                                    borderRadius: "var(--card-radius)",
                                    background: "var(--surface-glass)",
                                    borderColor: "var(--border-color)",
                                    boxShadow: "var(--shadow-card)",
                                    backdropFilter: "blur(16px) saturate(135%)",
                                }}
                            >
                                <button
                                    onClick={() => removeFromWatchlist(inst.symbol)}
                                    className="absolute top-2 right-2 text-xl"
                                    style={{ color: "var(--accent-gold)" }}
                                    title="Remove from current cap watchlist"
                                >
                                    x
                                </button>

                                <h3 className="text-lg font-bold">{inst.symbol}</h3>
                                <p className="text-xs" style={{ color: "var(--text-muted)" }}>{inst.instrument_key}</p>

                                <p className="text-xl mt-3 font-bold" style={{ color }}>
                                    Rs. {ltp !== "--" ? ltp.toFixed(2) : "--.--"}
                                </p>

                                <p className="text-sm font-semibold" style={{ color }}>
                                    {ltp === "--" ? "--" : `${change.toFixed(2)} (${percent.toFixed(2)}%)`}
                                </p>

                                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                                    {ltp === "--" ? "Waiting for ticks..." : "Real-time update"}
                                </p>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
