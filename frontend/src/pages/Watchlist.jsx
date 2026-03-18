import React, { useEffect, useState, useRef } from "react";
import { useTheme } from "../context/ThemeContext";

export default function Watchlist() {
    const { theme } = useTheme();
    const isLight = theme === "light";

    const [watchlist, setWatchlist] = useState([]);
    const [prices, setPrices] = useState({});
    const [priceChange, setPriceChange] = useState({});

    const wsRef = useRef(null);
    const reconnectRef = useRef(null);
    const mountedRef = useRef(false);

    // Load saved watchlist
    useEffect(() => {
        const saved = localStorage.getItem("watchlist");
        if (saved) setWatchlist(JSON.parse(saved));
    }, []);

    // WebSocket connection
    useEffect(() => {
        if (mountedRef.current) return;
        mountedRef.current = true;

        function connectWS() {
            if (wsRef.current) return;

            console.log("🔄 Connecting → ws://localhost:9000");
            const ws = new WebSocket("ws://localhost:9000");
            wsRef.current = ws;

            ws.onopen = () => {
                console.log("🟢 WS Connected");

                const keys = watchlist.map((x) => x.instrument_key);
                if (keys.length > 0) {
                    ws.send(JSON.stringify({ subscribe: keys }));
                    console.log("📡 Subscribed:", keys);
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
                        const percent = (change / prevClose) * 100;

                        const trend =
                            change > 0 ? "up" :
                                change < 0 ? "down" :
                                    "neutral";

                        newPrices[ik] = { ltp, change, percent };
                        newTrends[ik] = trend;
                    });

                    setPrices((prev) => ({ ...prev, ...newPrices }));
                    setPriceChange((prev) => ({ ...prev, ...newTrends }));

                } catch (e) {
                    console.error("WS parse error:", e);
                }
            };

            ws.onclose = () => {
                console.warn("🔴 WS Closed → reconnect in 2s...");
                wsRef.current = null;
                reconnectRef.current = setTimeout(connectWS, 2000);
            };
        }

        connectWS();

        return () => {
            if (wsRef.current) wsRef.current.close();
            clearTimeout(reconnectRef.current);
        };
    }, [watchlist.length]);

    // Resubscribe on watchlist change
    useEffect(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            const keys = watchlist.map((x) => x.instrument_key);
            wsRef.current.send(JSON.stringify({ subscribe: keys }));
            console.log("📡 Re-subscribed:", keys);
        }
    }, [watchlist]);

    // REMOVE STOCK + UNSUBSCRIBE
    const removeFromWatchlist = (symbol) => {
        const updated = watchlist.filter((s) => s.symbol !== symbol);
        setWatchlist(updated);
        localStorage.setItem("watchlist", JSON.stringify(updated));

        // 🔥🔥🔥 SEND UNSUBSCRIBE TO SERVER
        const removedItem = watchlist.find((s) => s.symbol === symbol);
        if (removedItem && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(
                JSON.stringify({
                    unsubscribe: [removedItem.instrument_key]
                })
            );
            console.log("❌ Unsubscribed:", removedItem.instrument_key);
        }
    };

    return (
        <div className={`p-6 min-h-screen ${isLight ? "bg-gray-50 text-gray-900" : "bg-[#0b0f19] text-gray-100"}`}>

            <h2 className={`text-3xl font-bold mb-6 ${isLight ? "text-yellow-600" : "text-yellow-400"}`}>
                ⭐ My Watchlist
            </h2>

            {watchlist.length === 0 ? (
                <p className="text-center mt-20 text-gray-400">Your watchlist is empty!</p>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                    {watchlist.map((inst) => {
                        const key = inst.instrument_key;
                        const info = prices[key] || {};

                        const ltp = info.ltp ?? "--";
                        const change = info.change ?? 0;
                        const percent = info.percent ?? 0;

                        const trend = priceChange[key];
                        const color =
                            trend === "up" ? "text-green-500"
                                : trend === "down" ? "text-red-500"
                                    : "text-blue-400";

                        return (
                            <div
                                key={key}
                                className={`relative rounded-lg p-4 shadow-md border ${isLight ? "bg-white border-gray-200" : "bg-[#161b22] border-gray-700"}`}
                            >
                                <button
                                    onClick={() => removeFromWatchlist(inst.symbol)}
                                    className="absolute top-2 right-2 text-yellow-400 text-xl"
                                >
                                    ★
                                </button>

                                <h3 className="text-lg font-bold">{inst.symbol}</h3>
                                <p className="text-xs text-gray-400">{inst.instrument_key}</p>

                                <p className={`text-xl mt-3 font-bold ${color}`}>
                                    ₹ {ltp !== "--" ? ltp.toFixed(2) : "--.--"}
                                </p>

                                <p className={`text-sm font-semibold ${color}`}>
                                    {ltp === "--" ? "--" : `${change.toFixed(2)} (${percent.toFixed(2)}%)`}
                                </p>

                                <p className="text-xs text-gray-400">
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
