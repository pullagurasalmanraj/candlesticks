export const INDEX_LIST = [
    {
        name: "Nifty 50",
        symbol: "NIFTY",
        display: "Nifty 50",
        instrumentKey: "NSE_INDEX|Nifty 50",
    },
    {
        name: "Sensex",
        symbol: "SENSEX",
        display: "Sensex",
        instrumentKey: "BSE_INDEX|SENSEX",
    },
    {
        name: "Bank Nifty",
        symbol: "BANKNIFTY",
        display: "Bank Nifty",
        instrumentKey: "NSE_INDEX|Nifty Bank",
    },
    {
        name: "Nifty Next 50",
        symbol: "NEXT50",
        display: "Nifty Next 50",
        instrumentKey: "NSE_INDEX|Nifty Next 50",
    },
];

export const INDEX_DEFAULTS = {
    NIFTY: { ltp: "--", change: 0, percent: 0 },
    BANKNIFTY: { ltp: "--", change: 0, percent: 0 },
    SENSEX: { ltp: "--", change: 0, percent: 0 },
    NEXT50: { ltp: "--", change: 0, percent: 0 },
};

export const INDEX_KEY_TO_SYMBOL = INDEX_LIST.reduce((acc, idx) => {
    const key = idx.instrumentKey?.toUpperCase?.();
    if (key) acc[key] = idx.symbol;
    return acc;
}, {});

export const INDEX_NAME_TO_SYMBOL = INDEX_LIST.reduce((acc, idx) => {
    if (idx.name) acc[idx.name] = idx.symbol;
    return acc;
}, {});
