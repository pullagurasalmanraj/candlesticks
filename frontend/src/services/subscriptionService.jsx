export async function subscribeSymbol(symbol) {
    const res = await fetch(
        `/api/ws-subscribe?symbol=${encodeURIComponent(symbol)}`
    );

    if (!res.ok) {
        throw new Error("Subscription failed");
    }

    return res.json().catch(() => ({}));
}

export async function unsubscribeInstrument(instrumentKey) {
    const res = await fetch("/api/unsubscribe", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            instrument_key: instrumentKey
        })
    });

    if (!res.ok) {
        throw new Error("Unsubscribe failed");
    }

    return res.json().catch(() => ({}));
}