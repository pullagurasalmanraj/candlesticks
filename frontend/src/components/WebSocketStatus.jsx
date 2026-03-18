import React, { memo } from "react";

// memo() — prevents re-render when Dashboard re-renders on every
// search keystroke. Only re-renders if isConnected actually changes.
const WebSocketStatus = memo(function WebSocketStatus({ isConnected, connectWebSocket, disconnectWebSocket }) {
    return (
        <button
            onClick={isConnected ? disconnectWebSocket : connectWebSocket}
            style={{
                display:      "inline-flex",
                alignItems:   "center",
                gap:          8,
                padding:      "6px 14px",
                borderRadius: "var(--button-radius)",
                border:       isConnected
                    ? "1px solid rgba(0,230,118,0.4)"
                    : "1px solid var(--border-color)",
                background:   isConnected ? "var(--accent-up)"   : "var(--bg-tertiary)",
                color:        isConnected ? "#fff"                : "var(--text-secondary)",
                fontSize:     "0.75rem",
                fontWeight:   600,
                fontFamily:   "var(--font-body)",
                cursor:       "pointer",
                transition:   "all 0.15s ease",
            }}
            onMouseEnter={e => e.currentTarget.style.opacity = "0.85"}
            onMouseLeave={e => e.currentTarget.style.opacity = "1"}
        >
            <span style={{
                width:        8, height: 8,
                borderRadius: "50%",
                background:   isConnected ? "#fff" : "var(--accent-down)",
                boxShadow:    isConnected ? "0 0 6px rgba(255,255,255,0.8)" : "none",
                animation:    isConnected ? "pulse 2s infinite" : "none",
                flexShrink:   0,
            }} />
            {isConnected ? "Disconnect WebSocket" : "Connect WebSocket"}
        </button>
    );
});

export default WebSocketStatus;
