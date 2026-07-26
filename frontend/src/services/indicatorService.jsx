export async function generateIndicators(symbol, timeframe, force = false) {

    const normalizeTF = (tf) => {
        const t = tf.toString().toLowerCase();

        const map = {
            "1": "1m",
            "3": "3m",
            "5": "5m",
            "15": "15m",
            "30": "30m",
            "60": "60m",
            "1d": "1d",
            "1440": "1d"
        };

        return map[t] || t;
    };

    const finalTF = normalizeTF(timeframe);
    const isDaily = finalTF === "1d";
    const forceParam = force ? "&force=true" : "";

    const url = isDaily
        ? `/api/indicators/daily?symbol=${symbol}&store=true${forceParam}`
        : `/api/indicators/intraday?symbol=${symbol}&timeframe=${finalTF}&store=true${forceParam}`;

    const res = await fetch(url);
    const data = await res.json();

    if (!res.ok || data.error) {
        throw new Error(data.error || "Indicator processing failed");
    }

    return data;
}