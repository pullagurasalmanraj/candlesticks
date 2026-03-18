import { normalizeDate } from "../utils/dateUtils";


export async function downloadExcelAPI({
  instrument_key,
  symbol,
  startDate,
  endDate
}) {

  const s = normalizeDate(startDate);
  const e = normalizeDate(endDate);

  const url = `/api/history/daily?instrument_key=${encodeURIComponent(
    instrument_key
  )}&symbol=${encodeURIComponent(symbol)}&start=${s}&end=${e}&_=${Date.now()}`;

  const res = await fetch(url);

  const type = res.headers.get("content-type") || "";

  if (type.includes("application/json")) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || "Server error");
  }

  const blob = await res.blob();

  return blob;
}