import { useEffect, useRef, useState, useCallback } from "react";
import { INDEX_KEY_TO_SYMBOL } from "../context/indexes";

const WS_URL = "ws://localhost:9000";

const CLEANED_INDEX_SYMBOLS = {
    NIFTY: "NIFTY",
    NIFTY50: "NIFTY",
    BANKNIFTY: "BANKNIFTY",
    SENSEX: "SENSEX",
    NIFTYNEXT50: "NEXT50",
    NEXT50: "NEXT50",
};

function normalizeFeedKey(rawKey) {
    return String(rawKey || "").trim().toUpperCase();
}

function resolveIndexAlias(feedKey) {
    if (!feedKey) return null;

    if (INDEX_KEY_TO_SYMBOL[feedKey]) {
        return INDEX_KEY_TO_SYMBOL[feedKey];
    }

    const token = feedKey.includes("|")
        ? feedKey.split("|").pop()
        : feedKey;

    const cleaned = token.replace(/[^A-Z0-9]/g, "");
    return CLEANED_INDEX_SYMBOLS[cleaned] || null;
}

function extractLtpc(feed) {
    const full = feed?.fullFeed;
    if (!full) return null;
    return full.marketFF?.ltpc || full.indexFF?.ltpc || null;
}

function buildTick(ltpc) {
    const ltp = Number(ltpc?.ltp);
    const prevClose = Number(ltpc?.cp);

    if (!isFinite(ltp)) return null;

    const base = prevClose > 0 ? prevClose : ltp;
    const change = +(ltp - base).toFixed(2);
    const percent = base > 0 ? +((change / base) * 100).toFixed(2) : 0;

    return {
        ltp,
        change,
        percent,
        direction: change >= 0 ? "up" : "down",
        ts: Date.now(),
    };
}

export default function useWebSocketPrices(_instrumentByKey) {
    const [prices, setPrices] = useState({});
    const [lastPrices, setLastPrices] = useState({});
    const [isConnected, setIsConnected] = useState(false);
    const [isLoading, setIsLoading] = useState(true);

    const wsRef = useRef(null);
    const closedRef = useRef(false);
    const reconnectTimerRef = useRef(null);

    useEffect(() => {
        const cached = localStorage.getItem("lastPrices");
        if (!cached) return;

        try {
            const parsed = JSON.parse(cached);
            setPrices(parsed);
            setLastPrices(parsed);
        } catch {
            // ignore malformed cache
        }
    }, []);

    const handleMessage = useCallback((evt) => {
        try {
            const msg = JSON.parse(evt.data);
            const feeds = msg?.data?.feeds;
            if (!feeds) return;

            const updatedPrices = {};

            for (const [rawKey, feed] of Object.entries(feeds)) {
                const normalizedKey = normalizeFeedKey(rawKey);
                if (!normalizedKey) continue;

                const ltpc = extractLtpc(feed);
                if (!ltpc) continue;

                const tick = buildTick(ltpc);
                if (!tick) continue;

                updatedPrices[normalizedKey] = tick;

                const indexAlias = resolveIndexAlias(normalizedKey);
                if (indexAlias) {
                    updatedPrices[indexAlias] = tick;
                }
            }

            if (Object.keys(updatedPrices).length === 0) return;

            setPrices((prev) => {
                const merged = { ...prev, ...updatedPrices };
                try {
                    localStorage.setItem("lastPrices", JSON.stringify(merged));
                } catch {
                    // storage might be full or disabled
                }
                return merged;
            });

            setLastPrices((prev) => ({ ...prev, ...updatedPrices }));
        } catch (err) {
            console.error("Tick parse error:", err);
        }
    }, []);

    const openSocket = useCallback(() => {
        if (closedRef.current) return;

        const current = wsRef.current;
        if (
            current &&
            (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)
        ) {
            return;
        }

        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }

        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
            setIsLoading(false);
        };

        ws.onmessage = handleMessage;

        ws.onclose = () => {
            setIsConnected(false);

            if (!closedRef.current) {
                reconnectTimerRef.current = setTimeout(() => {
                    openSocket();
                }, 2000);
            }
        };

        ws.onerror = () => {
            console.warn("WS temporary error");
        };
    }, [handleMessage]);

    useEffect(() => {
        closedRef.current = false;
        openSocket();

        return () => {
            closedRef.current = true;
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
                reconnectTimerRef.current = null;
            }
            wsRef.current?.close();
        };
    }, [openSocket]);

    const connectWebSocket = useCallback(() => {
        closedRef.current = false;
        openSocket();
    }, [openSocket]);

    const disconnectWebSocket = useCallback(() => {
        closedRef.current = true;

        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }

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
