import { format } from "date-fns";
import { formatYMD } from "../utils/dateUtils";

export async function fetchHistoricalCandlesAPI({
    symbol,
    instrument_key,
    timeframe,
    histStart,
    histEnd
}) {

    const s = formatYMD(histStart);
    const e = formatYMD(histEnd);

    const todayStr = format(new Date(), "yyyy-MM-dd");
    const isTodayRange = s === todayStr && e === todayStr;

    let endpoint = "";
    let payload = {
        symbol,
        instrument_key,
        start_date: s,
        end_date: e
    };

    if (["1D", "1DAY", "DAY", "1440"].includes(timeframe)) {
        endpoint = "/api/candles/daily";
    }
    else if (isTodayRange) {
        endpoint = "/api/candles/store";
        payload.timeframe = timeframe;
    }
    else {
        endpoint = "/api/candles/history";
        payload.timeframe = timeframe;
    }

    const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    const result = await res.json();

    if (!res.ok) {
        throw new Error(result.error || "API error");
    }

    return result;
}

export async function storeCandlesAPI(payload, timeframe) {

    let endpoint = "";

    if (["1440", "1D", "1d", "DAY", "day"].includes(timeframe)) {

        endpoint = "/api/candles/daily";

    } else {

        endpoint = "/api/candles/history";
        payload.timeframe = timeframe;

    }

    const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    const result = await res.json();

    if (!res.ok) {
        throw new Error(result.error || "API error");
    }

    return result;
}