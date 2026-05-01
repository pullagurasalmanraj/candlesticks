export async function subscribeInstruments(instrumentKeys, options = {}) {
    const keys = Array.isArray(instrumentKeys)
        ? instrumentKeys
        : [instrumentKeys];
    const cleaned = [...new Set(
        keys
            .map((k) => String(k || "").trim())
            .filter(Boolean)
    )];

    if (cleaned.length === 0) {
        throw new Error("No instrument keys provided");
    }

    const res = await fetch("/api/ws-subscribe", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            instrument_keys: cleaned,
            replace: !!options.replace,
        }),
    });

    if (!res.ok) {
        throw new Error("Subscription failed");
    }

    return res.json().catch(() => ({}));
}

export async function subscribeSymbol(symbol, options = {}) {
    return subscribeInstruments([symbol], options);
}

export async function unsubscribeInstrument(instrumentKey) {
    const res = await fetch("/api/unsubscribe", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            instrument_keys: [instrumentKey]
        })
    });

    if (!res.ok) {
        throw new Error("Unsubscribe failed");
    }

    return res.json().catch(() => ({}));
}

export async function unsubscribeAllInstruments() {
    const res = await fetch("/api/unsubscribe-all", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
    });

    if (!res.ok) {
        throw new Error("Unsubscribe all failed");
    }

    return res.json().catch(() => ({}));
}
