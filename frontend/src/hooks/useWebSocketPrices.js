import { useEffect, useRef, useState, useCallback } from "react";

export default function useWebSocketPrices(instrumentByKey) {

    const [prices,      setPrices]      = useState({});
    const [lastPrices,  setLastPrices]  = useState({});
    const [isConnected, setIsConnected] = useState(false);
    const [isLoading,   setIsLoading]   = useState(true);

    const wsRef    = useRef(null);
    const closedRef = useRef(false);   // tracks intentional close

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
    }, []); // runs once

    // ── WebSocket connection ──────────────────────────────────────
    // ✅ NO dependency on instrumentByKey — the socket does NOT need
    //    to restart when instruments change. It reads subscriptions
    //    from localStorage directly.
    // ✅ Empty deps [] = opens once on mount, cleans up on unmount.
    useEffect(() => {
        closedRef.current = false;

        const connect = () => {

            if (closedRef.current) return; // don't reconnect after unmount

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
                    ws.send(JSON.stringify({
                        subscribe: keys,
                        source:    "restore"
                    }));
                }
            };

            ws.onmessage = (evt) => {
                try {
                    const msg   = JSON.parse(evt.data);
                    const feeds = msg?.data?.feeds;
                    if (!feeds) return;

                    const updatedPrices = {};

                    for (const [rawKey, feed] of Object.entries(feeds)) {
                        const ltpc = feed?.fullFeed?.marketFF?.ltpc;
                        if (!ltpc) continue;

                        const ltp       = Number(ltpc.ltp);
                        const prevClose = Number(ltpc.cp);
                        if (!isFinite(ltp) || !isFinite(prevClose)) continue;

                        const change  = +(ltp - prevClose).toFixed(2);
                        const percent = +((change / prevClose) * 100).toFixed(2);

                        updatedPrices[rawKey.trim().toUpperCase()] = {
                            ltp, change, percent,
                            direction: change >= 0 ? "up" : "down",
                            ts: Date.now(),
                        };
                    }

                    if (Object.keys(updatedPrices).length > 0) {
                        setPrices(prev => {
                            const merged = { ...prev, ...updatedPrices };
                            localStorage.setItem("lastPrices", JSON.stringify(merged));
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
                // Auto-reconnect only if not intentionally closed
                if (!closedRef.current) {
                    setTimeout(connect, 2000);
                }
            };

            ws.onerror = () => {
                console.warn("WS temporary error");
            };
        };

        connect();

        // Cleanup — marks as intentionally closed so reconnect stops
        return () => {
            closedRef.current = true;
            wsRef.current?.close();
        };

    }, []); // ← empty array: socket opens ONCE, never restarts on re-render

    // ── Manual connect / disconnect (for WebSocketStatus button) ──
    const connectWebSocket = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;
        closedRef.current = false;

        const ws = new WebSocket("ws://localhost:9000");
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
            setIsLoading(false);
            const savedSubs = JSON.parse(localStorage.getItem("activeSubscriptions") || "{}");
            const keys = Object.keys(savedSubs);
            if (keys.length > 0) {
                ws.send(JSON.stringify({ subscribe: keys, source: "manual" }));
            }
        };

        ws.onmessage = wsRef.current?.onmessage; // reuse same handler
        ws.onclose   = () => { setIsConnected(false); };
        ws.onerror   = () => { console.warn("WS error"); };
    }, []);

    const disconnectWebSocket = useCallback(() => {
        closedRef.current = true;  // prevents auto-reconnect
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
