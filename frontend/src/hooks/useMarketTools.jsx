import { format } from "date-fns";
import { formatYMD, normalizeDate } from "../utils/dateUtils";

export default function useMarketTools({
    selectedSymbol,
    selectedInstrument,
    timeframe,
    histStart,
    histEnd,
    startDate,
    endDate,
    years,
    setToast,
    setIsFetchingHistory,
    setIsApplyingIndicators
}) {

    const applyIndicators = async () => {

        if (!selectedSymbol || !timeframe) {
            return setToast("Select a symbol and timeframe first.");
        }

        setIsApplyingIndicators(true);

        const tf = timeframe === "1440" ? "1d" : timeframe;

        const url = tf === "1d"
            ? `/api/indicators/daily?symbol=${selectedSymbol}&store=true`
            : `/api/indicators/intraday?symbol=${selectedSymbol}&timeframe=${tf}&store=true`;

        try {

            const res = await fetch(url);
            const data = await res.json();

            if (!res.ok || data.error) {
                return setToast(data.error || "Indicator processing failed");
            }

            setToast(`Saved ${data.count || data.rows || 0} rows`);

        } catch {
            setToast("Indicator error");
        } finally {
            setIsApplyingIndicators(false);
        }
    };

    const downloadExcel = async () => {

        if (!selectedSymbol || !startDate || !endDate) {
            return setToast("Select symbol and date range.");
        }

        const key = selectedInstrument.instrument_key;

        const s = normalizeDate(startDate);
        const e = normalizeDate(endDate);

        const url =
            `/api/history/daily?instrument_key=${encodeURIComponent(key)}` +
            `&symbol=${encodeURIComponent(selectedSymbol)}` +
            `&start=${s}&end=${e}&_=${Date.now()}`;

        const res = await fetch(url);

        const blob = await res.blob();

        const fileURL = window.URL.createObjectURL(blob);

        const a = document.createElement("a");

        a.href = fileURL;

        a.download = `${selectedSymbol}_${s}_${e}.xlsx`;

        document.body.appendChild(a);

        a.click();

        a.remove();
    };

    return { applyIndicators, downloadExcel };
}