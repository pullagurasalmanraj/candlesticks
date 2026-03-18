import React, { useState, useEffect, memo } from "react";

// ── Consistent color per symbol for fallback initials ────────────
const COLORS = [
    ["#4f9eff", "#0d1526"],
    ["#00e676", "#0d261a"],
    ["#ffd54f", "#261e0d"],
    ["#ff8a65", "#261309"],
    ["#ce93d8", "#1a0d26"],
    ["#80deea", "#0d2226"],
    ["#ef9a9a", "#260d0d"],
];

function symbolColor(sym) {
    let hash = 0;
    for (let i = 0; i < sym.length; i++) hash += sym.charCodeAt(i);
    return COLORS[hash % COLORS.length];
}

function getInitials(sym) {
    if (!sym) return "??";
    return sym.trim().toUpperCase().slice(0, 2);
}

// ── Batch logo resolver ───────────────────────────────────────────
// All StockLogo instances share this singleton.
// Instead of 50 components firing 50 requests, they register here
// and a single batch call fires after a 30ms debounce window.

const logoCache   = {};   // symbol → url string | null | "pending"
const subscribers = {};   // symbol → Set of callback functions
let   batchTimer  = null;
const pendingBatch = new Set();

function subscribeToLogo(symbol, callback) {
    const sym = symbol.toUpperCase().trim().replace(/-EQ$/, "").replace(/&/g, "").replace(/_/g, "");

    // Already resolved — call back immediately
    if (logoCache[sym] !== undefined && logoCache[sym] !== "pending") {
        callback(logoCache[sym]);
        return () => {};
    }

    // Register subscriber
    if (!subscribers[sym]) subscribers[sym] = new Set();
    subscribers[sym].add(callback);

    // Queue for batch if not already pending/resolved
    if (logoCache[sym] === undefined) {
        logoCache[sym] = "pending";
        pendingBatch.add(sym);

        // Debounce — collect all symbols registered within 30ms into one batch call
        clearTimeout(batchTimer);
        batchTimer = setTimeout(flushBatch, 30);
    }

    // Return unsubscribe function
    return () => {
        if (subscribers[sym]) subscribers[sym].delete(callback);
    };
}

async function flushBatch() {
    if (pendingBatch.size === 0) return;

    const symbols = [...pendingBatch];
    pendingBatch.clear();

    try {
        const res = await fetch("/api/logo/batch", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify({ symbols }),
        });

        if (!res.ok) throw new Error(`batch failed: ${res.status}`);

        const { logos } = await res.json();

        // Notify all subscribers
        for (const sym of symbols) {
            const domain = logos[sym];   // url string or null
            logoCache[sym] = domain || null;

            if (subscribers[sym]) {
                subscribers[sym].forEach(cb => cb(logoCache[sym]));
                subscribers[sym].clear();
            }
        }
    } catch (err) {
        // On failure mark all as null so components fall back to initials
        for (const sym of symbols) {
            logoCache[sym] = null;
            if (subscribers[sym]) {
                subscribers[sym].forEach(cb => cb(null));
                subscribers[sym].clear();
            }
        }
    }
}

// ── Component ─────────────────────────────────────────────────────
const StockLogo = memo(function StockLogo({
    symbol,
    size = 28,
    borderRadius = 6,
    style = {},
}) {
    const sym = (symbol || "").toUpperCase().trim()
        .replace(/-EQ$/, "")
        .replace(/&/g, "")
        .replace(/_/g, "");

    const initials    = getInitials(sym);
    const [bg, fg]    = symbolColor(sym);

    // logoUrl states: undefined = loading, null = failed/no logo, string = url
    const [logoUrl, setLogoUrl] = useState(() => {
        const cached = logoCache[sym];
        return cached === "pending" ? undefined : cached;
    });
    const [imgFailed, setImgFailed] = useState(false);

    useEffect(() => {
        if (!sym) return;

        // Already resolved in cache
        const cached = logoCache[sym];
        if (cached !== undefined && cached !== "pending") {
            setLogoUrl(cached);
            return;
        }

        // Subscribe to batch resolution
        const unsub = subscribeToLogo(sym, (url) => {
            setLogoUrl(url);
        });

        return unsub;
    }, [sym]);

    const showInitials = imgFailed || logoUrl === null || logoUrl === undefined;

    const initialsEl = (
        <div style={{
            width:          size,
            height:         size,
            borderRadius,
            background:     bg,
            color:          fg,
            display:        "flex",
            alignItems:     "center",
            justifyContent: "center",
            fontSize:       Math.max(9, size * 0.33) + "px",
            fontWeight:     700,
            fontFamily:     "var(--font-display)",
            flexShrink:     0,
            userSelect:     "none",
            letterSpacing:  "-0.01em",
            ...style,
        }}>
            {initials}
        </div>
    );

    // Still loading — show initials as placeholder (no layout shift)
    if (logoUrl === undefined) return initialsEl;

    // Confirmed no logo
    if (showInitials) return initialsEl;

    return (
        <img
            src={logoUrl}
            alt={sym}
            width={size}
            height={size}
            onError={() => setImgFailed(true)}
            style={{
                width:      size,
                height:     size,
                borderRadius,
                objectFit:  "contain",
                background: "var(--bg-secondary)",
                flexShrink: 0,
                display:    "block",
                ...style,
            }}
        />
    );
});

export default StockLogo;
