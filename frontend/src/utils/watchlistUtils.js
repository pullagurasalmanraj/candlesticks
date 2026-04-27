export const WATCHLIST_STORAGE_KEY = "watchlistsByCap";
export const WATCHLIST_LEGACY_KEY = "watchlist";
export const DEFAULT_WATCHLIST_CAP = "large";

export const WATCHLIST_CAP_OPTIONS = [
    { key: "small", label: "Small Cap" },
    { key: "mid", label: "Mid Cap" },
    { key: "large", label: "Large Cap" },
];

export const WATCHLIST_CAP_KEYS = WATCHLIST_CAP_OPTIONS.map((opt) => opt.key);

export function normalizeSymbol(value) {
    return String(value || "").trim().toUpperCase();
}

export function getWatchlistCapLabel(capKey) {
    const found = WATCHLIST_CAP_OPTIONS.find((item) => item.key === capKey);
    return found ? found.label : "Watchlist";
}

function normalizeWatchlistItem(item, fallbackCap = DEFAULT_WATCHLIST_CAP) {
    if (!item || typeof item !== "object") return null;

    const symbol = normalizeSymbol(item.symbol);
    if (!symbol) return null;

    const cap = WATCHLIST_CAP_KEYS.includes(item.cap) ? item.cap : fallbackCap;
    return {
        ...item,
        symbol,
        cap,
    };
}

export function ensureWatchlistsShape(value) {
    const source = value && typeof value === "object" ? value : {};
    const next = {};
    const seen = new Set();

    WATCHLIST_CAP_KEYS.forEach((cap) => {
        const items = Array.isArray(source[cap]) ? source[cap] : [];
        next[cap] = [];

        items.forEach((item) => {
            const normalized = normalizeWatchlistItem(item, cap);
            if (!normalized) return;
            if (seen.has(normalized.symbol)) return;
            seen.add(normalized.symbol);
            next[cap].push(normalized);
        });
    });

    return next;
}

export function flattenWatchlistsByCap(watchlistsByCap) {
    const safe = ensureWatchlistsShape(watchlistsByCap);
    const all = [];

    WATCHLIST_CAP_KEYS.forEach((cap) => {
        safe[cap].forEach((item) => all.push(item));
    });

    return all;
}

export function findWatchlistCapBySymbol(watchlistsByCap, symbol) {
    const sym = normalizeSymbol(symbol);
    if (!sym) return null;

    const safe = ensureWatchlistsShape(watchlistsByCap);
    for (const cap of WATCHLIST_CAP_KEYS) {
        if (safe[cap].some((item) => item.symbol === sym)) {
            return cap;
        }
    }

    return null;
}

export function readStoredWatchlistsByCap() {
    try {
        const raw = localStorage.getItem(WATCHLIST_STORAGE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            return ensureWatchlistsShape(parsed);
        }
    } catch {
        // ignore invalid persisted shape
    }

    try {
        const legacyRaw = localStorage.getItem(WATCHLIST_LEGACY_KEY);
        if (legacyRaw) {
            const parsed = JSON.parse(legacyRaw);
            if (Array.isArray(parsed)) {
                return ensureWatchlistsShape({
                    [DEFAULT_WATCHLIST_CAP]: parsed.map((item) =>
                        normalizeWatchlistItem(item, DEFAULT_WATCHLIST_CAP)
                    ),
                });
            }
        }
    } catch {
        // ignore invalid legacy shape
    }

    return ensureWatchlistsShape({});
}
