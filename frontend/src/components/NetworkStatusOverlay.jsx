import React, { useState, useEffect, useCallback } from "react";
import { Wifi, WifiOff, ServerCrash, RefreshCw, AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

export default function NetworkStatusOverlay() {
    const [isOnline, setIsOnline] = useState(navigator.onLine);
    const [serverHealthy, setServerHealthy] = useState(true);
    const [isChecking, setIsChecking] = useState(false);
    const [dismissed, setDismissed] = useState(false);
    const [reconnectCountdown, setReconnectCountdown] = useState(5);

    // Ping backend to distinguish Client Internet Disconnect vs Server Engine Disconnect
    const checkServerHealth = useCallback(async () => {
        if (!navigator.onLine) {
            setIsOnline(false);
            return;
        }
        setIsOnline(true);
        setIsChecking(true);

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 4000);
            const res = await fetch("/api/auth/status", { signal: controller.signal });
            clearTimeout(timeoutId);

            if (res.ok || res.status === 200 || res.status === 401) {
                setServerHealthy(true);
                setDismissed(false);
            } else {
                setServerHealthy(false);
            }
        } catch (err) {
            // If fetch failed while user is online, it is our server/engine side problem
            if (navigator.onLine) {
                setServerHealthy(false);
            }
        } finally {
            setIsChecking(false);
        }
    }, []);

    useEffect(() => {
        const handleOnline = () => {
            setIsOnline(true);
            setDismissed(false);
            checkServerHealth();
        };

        const handleOffline = () => {
            setIsOnline(false);
            setDismissed(false);
        };

        window.addEventListener("online", handleOnline);
        window.addEventListener("offline", handleOffline);

        // Periodic health check every 15 seconds
        const interval = setInterval(checkServerHealth, 15000);

        return () => {
            window.removeEventListener("online", handleOnline);
            window.removeEventListener("offline", handleOffline);
            clearInterval(interval);
        };
    }, [checkServerHealth]);

    // Auto-reconnect countdown timer when disconnected
    useEffect(() => {
        if (isOnline && serverHealthy) {
            setReconnectCountdown(5);
            return;
        }

        const timer = setInterval(() => {
            setReconnectCountdown((prev) => {
                if (prev <= 1) {
                    checkServerHealth();
                    return 5;
                }
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(timer);
    }, [isOnline, serverHealthy, checkServerHealth]);

    // If completely normal, don't show anything
    if (isOnline && serverHealthy) {
        return null;
    }

    const isClientOffline = !isOnline;
    const isServerProblem = isOnline && !serverHealthy;

    return (
        <div style={{
            position: "fixed",
            top: 16,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 99999,
            maxWidth: "680px",
            width: "calc(100% - 32px)",
            pointerEvents: "auto",
            animation: "slideDown 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        }}>
            <div style={{
                background: isClientOffline
                    ? "rgba(239, 68, 68, 0.95)"
                    : "rgba(245, 158, 11, 0.95)",
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                border: isClientOffline
                    ? "1px solid rgba(255, 255, 255, 0.3)"
                    : "1px solid rgba(255, 255, 255, 0.3)",
                boxShadow: isClientOffline
                    ? "0 12px 36px rgba(239, 68, 68, 0.35), 0 0 20px rgba(239, 68, 68, 0.2)"
                    : "0 12px 36px rgba(245, 158, 11, 0.35), 0 0 20px rgba(245, 158, 11, 0.2)",
                borderRadius: 14,
                padding: "14px 18px",
                color: "#FFFFFF",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 14,
                flexWrap: "wrap",
            }}>
                {/* Left Animated Icon & Diagnostics */}
                <div style={{ display: "flex", alignItems: "center", gap: 14, flex: 1, minWidth: "260px" }}>
                    <div style={{
                        position: "relative",
                        width: 44,
                        height: 44,
                        borderRadius: "50%",
                        background: "rgba(0, 0, 0, 0.2)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                    }}>
                        {/* Radar Pulse Rings */}
                        <div style={{
                            position: "absolute",
                            inset: -4,
                            borderRadius: "50%",
                            border: "2px solid rgba(255,255,255,0.6)",
                            animation: "radarPing 1.8s cubic-bezier(0, 0.2, 0.8, 1) infinite",
                        }} />
                        <div style={{
                            position: "absolute",
                            inset: -8,
                            borderRadius: "50%",
                            border: "1px solid rgba(255,255,255,0.3)",
                            animation: "radarPing 1.8s cubic-bezier(0, 0.2, 0.8, 1) infinite",
                            animationDelay: "0.5s",
                        }} />

                        {isClientOffline ? (
                            <WifiOff size={22} color="#FFFFFF" />
                        ) : (
                            <ServerCrash size={22} color="#FFFFFF" />
                        )}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <div style={{
                            fontSize: "0.9rem",
                            fontWeight: 800,
                            letterSpacing: "-0.01em",
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                        }}>
                            <span>
                                {isClientOffline
                                    ? "📡 Internet Connection Lost (Your Side)"
                                    : "🛠️ Market Feed Server Disconnected (Our Side Problem)"}
                            </span>
                        </div>

                        <div style={{
                            fontSize: "0.74rem",
                            opacity: 0.95,
                            lineHeight: 1.35,
                        }}>
                            {isClientOffline
                                ? "Please check your Wi-Fi, Ethernet, or Mobile Data. Live streaming will resume automatically when you're reconnected."
                                : "Your internet is active, but the local market data engine is restarting or synchronizing. Auto-reconnecting in " + reconnectCountdown + "s..."}
                        </div>
                    </div>
                </div>

                {/* Right Quick Action Button */}
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button
                        onClick={checkServerHealth}
                        disabled={isChecking}
                        style={{
                            background: "rgba(0, 0, 0, 0.25)",
                            border: "1px solid rgba(255, 255, 255, 0.4)",
                            color: "#FFFFFF",
                            padding: "7px 14px",
                            borderRadius: 8,
                            fontSize: "0.78rem",
                            fontWeight: 700,
                            cursor: isChecking ? "wait" : "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            transition: "all 0.2s ease",
                            whiteSpace: "nowrap",
                        }}
                    >
                        <RefreshCw
                            size={14}
                            style={{
                                animation: isChecking ? "spin 1s linear infinite" : "none",
                            }}
                        />
                        <span>{isChecking ? "Checking..." : "Retry Now"}</span>
                    </button>
                </div>
            </div>

            <style>{`
                @keyframes slideDown {
                    from { transform: translate(-50%, -40px); opacity: 0; }
                    to { transform: translate(-50%, 0); opacity: 1; }
                }
                @keyframes radarPing {
                    0% { transform: scale(0.9); opacity: 0.8; }
                    100% { transform: scale(1.6); opacity: 0; }
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `}</style>
        </div>
    );
}
