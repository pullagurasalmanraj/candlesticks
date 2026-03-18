import { useEffect, useRef, useState, useCallback } from "react";

export default function useWebSocketPrices(instrumentByKey) {

    const [prices, setPrices]           = useState({});
    const [lastPrices, setLastPrices]   = useState({});
    const [isConnected, setIsConnected] = useState(false);
    const [isLoading, setIsLoading]     = useState(true);

    const wsRef      = useRef(null);
    const closedRef  = useRef(false);

    // ── Restore cached prices on mount ───────────────────────────
    useEffect(() => {
        const cached = localStorage.getItem("lastPrices");
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                setPrices(parsed);
                setLastPrices(parsed);
            } catch { }
        }
    }, []);

    // ── Parse a single feed entry → { ltp, cp } ──────────────────
    // Handles both equity (marketFF) and index (indexFF)
    const extractLtpc = (feed) => {
        const full = feed?.fullFeed;
        if (!full) return null;
        // Equity
        if (full.marketFF?.ltpc) return full.marketFF.ltpc;
        // Index
        if (full.indexFF?.ltpc)  return full.indexFF.ltpc;
        return null;
    };

    // ── WebSocket connection ──────────────────────────────────────
    useEffect(() => {
        closedRef.current = false;

        const connect = () => {
            if (closedRef.current) return;

            const ws = new WebSocket("ws://localhost:9000");
            wsRef.current = ws;

            ws.onopen = () => {
                console.log("🟢 WS connected");
                setIsConnected(true);
                setIsLoading(false);

                // Restore active subscriptions from localStorage
                const savedSubs = JSON.parse(
                    localStorage.getItem("activeSubscriptions") || "{}"
                );
                const keys = Object.keys(savedSubs);
                if (keys.length > 0) {
                    ws.send(JSON.stringify({ subscribe: keys, source: "restore" }));
                }
            };

            ws.onmessage = (evt) => {
                try {
                    const msg   = JSON.parse(evt.data);
                    const feeds = msg?.data?.feeds;
                    if (!feeds) return;

                    const updatedPrices = {};

                    for (const [rawKey, feed] of Object.entries(feeds)) {
                        const ltpc = extractLtpc(feed);
                        if (!ltpc) continue;

                        const ltp       = Number(ltpc.ltp);
                        const prevClose = Number(ltpc.cp);   // closing price / prev close

                        if (!isFinite(ltp)) continue;

                        // prevClose may be 0 on first tick — fallback to ltp
                        const base    = prevClose > 0 ? prevClose : ltp;
                        const change  = +(ltp - base).toFixed(2);
                        const percent = base > 0 ? +((change / base) * 100).toFixed(2) : 0;

                        updatedPrices[rawKey.trim().toUpperCase()] = {
                            ltp,
                            change,
                            percent,
                            direction: change >= 0 ? "up" : "down",
                            ts: Date.now(),
                        };
                    }

                    if (Object.keys(updatedPrices).length > 0) {
                        setPrices(prev => {
                            const merged = { ...prev, ...updatedPrices };
                            try {
                                localStorage.setItem("lastPrices", JSON.stringify(merged));
                            } catch { }
                            return merged;
                        });
                        setLastPrices(prev => ({ ...prev, ...updatedPrices }));
                    }

                } catch (err) {
                    console.error("Tick parse error:", err);
                }
            };

            ws.onclose = () => {
                console.warn("🔴 WS closed");
                setIsConnected(false);
                if (!closedRef.current) {
                    setTimeout(connect, 2000);
                }
            };

            ws.onerror = () => {
                console.warn("WS temporary error");
            };
        };

        connect();

        return () => {
            closedRef.current = true;
            wsRef.current?.close();
        };
    }, []);

    // ── Manual controls ───────────────────────────────────────────
    const connectWebSocket = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;
        closedRef.current = false;

        const ws = new WebSocket("ws://localhost:9000");
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
            setIsLoading(false);
            const savedSubs = JSON.parse(
                localStorage.getItem("activeSubscriptions") || "{}"
            );
            const keys = Object.keys(savedSubs);
            if (keys.length > 0) {
                ws.send(JSON.stringify({ subscribe: keys, source: "manual" }));
            }
        };
        ws.onclose = () => setIsConnected(false);
        ws.onerror = () => console.warn("WS error");
    }, []);

    const disconnectWebSocket = useCallback(() => {
        closedRef.current = true;
        wsRef.current?.close();
        setIsConnected(false);
    }, []);

    return {
        prices,
        lastPrices,
        isConnected,
        isLoading,
        wsRef,
        connectWebSocket,
        disconnectWebSocket,
    };
}
