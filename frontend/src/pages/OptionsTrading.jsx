import { useMemo, useState } from "react";
import { useTheme } from "../context/ThemeContext";
import { Activity, Eye, TrendingUp, TrendingDown } from "lucide-react";

/* ---------------- MOCK OPTION CHAIN DATA ---------------- */
const EXPIRIES = ["29 May 2026", "05 Jun 2026", "12 Jun 2026", "19 Jun 2026"];

const MOCK_CHAIN = {
    symbol: "NIFTY",
    spot: 26146.55,
    change: +34.7,
    changePct: +0.13,
    vix: 9.19,
    iv: 11.8,
    maxPain: 26150,
    pcr: 0.94,
    chain: [
        { strike: 26000, pcr: 1.32, call: { ltp: 186.2, oi: 140.2, oiChange: 18.5, iv: 11.7 }, put: { ltp: 23.4, oi: 199.3, oiChange: 6.2, iv: 11.7 } },
        { strike: 26050, pcr: 1.07, call: { ltp: 152.0, oi: 178.4, oiChange: -6.0, iv: 10.3 }, put: { ltp: 36.4, oi: 232.0, oiChange: 25.0, iv: 10.3 } },
        { strike: 26100, pcr: 0.89, call: { ltp: 117.6, oi: 210.5, oiChange: 23.8, iv: 11.4 }, put: { ltp: 51.1, oi: 214.1, oiChange: 31.0, iv: 11.4 } },
        { strike: 26150, pcr: 0.71, call: { ltp: 86.4, oi: 184.0, oiChange: 59.6, iv: 12.1 }, put: { ltp: 70.2, oi: 173.2, oiChange: 74.5, iv: 12.1 } },
        { strike: 26200, pcr: 0.54, call: { ltp: 61.5, oi: 123.5, oiChange: 95.1, iv: 12.1 }, put: { ltp: 94.6, oi: 51.7, oiChange: 27.2, iv: 12.1 } },
        { strike: 26250, pcr: 0.38, call: { ltp: 42.8, oi: 98.4, oiChange: 118.6, iv: 11.9 }, put: { ltp: 123.2, oi: 42.8, oiChange: 9.6, iv: 11.9 } },
        { strike: 26300, pcr: 0.28, call: { ltp: 29.7, oi: 78.1, oiChange: 142.0, iv: 11.5 }, put: { ltp: 154.8, oi: 18.1, oiChange: 16.8, iv: 11.5 } }
    ]
};

const formatNumber = (value) => typeof value === "number" ? value.toFixed(2) : value;

export default function OptionsTrading() {
    const { theme } = useTheme();
    const isLight = theme === "light";

    const [symbol, setSymbol] = useState(MOCK_CHAIN.symbol);
    const [expiry, setExpiry] = useState(EXPIRIES[0]);
    const [orderType, setOrderType] = useState("Market");
    const [side, setSide] = useState("Buy");
    const [qty, setQty] = useState(75);
    const [price, setPrice] = useState(0);
    const [sortBy, setSortBy] = useState("strike");
    const [sortDirection, setSortDirection] = useState("asc");

    const data = useMemo(() => ({ ...MOCK_CHAIN, symbol }), [symbol]);

    const sortedChain = useMemo(() => {
        const chain = [...data.chain];
        chain.sort((a, b) => {
            if (sortBy === "strike") return sortDirection === "asc" ? a.strike - b.strike : b.strike - a.strike;
            return 0;
        });
        return chain;
    }, [data.chain, sortBy, sortDirection]);

    const atmStrike = Math.round(data.spot / 50) * 50;

    return (
        <div className="p-5 text-slate-100">
            <header className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-900/80 p-4 shadow-lg border border-slate-700">
                <div>
                    <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Options Trading</h1>
                    <p className="text-xs text-slate-400">Interactive option chain with order ticket and analytics callbacks</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-3 py-1 text-xs font-medium text-slate-200">LIVE · NSE Derivatives</span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-sky-700/20 px-3 py-1 text-xs font-medium text-sky-300"><Eye size={12} /> {data.symbol}</span>
                </div>
            </header>

            <section className="grid gap-4 lg:grid-cols-3">
                <div className="lg:col-span-2 grid gap-4">
                    <div className="rounded-xl border border-slate-700 bg-slate-900/75 p-4 shadow-md">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <h2 className="text-base font-semibold">{data.symbol} Option Chain</h2>
                                <p className="text-xs text-slate-400">Expiry: {expiry}</p>
                            </div>
                            <div className="flex items-center gap-2">
                                <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="rounded-md border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-50 outline-none focus:border-blue-500">
                                    {['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'RELIANCE', 'TCS'].map((s) => <option key={s} value={s}>{s}</option>)}
                                </select>
                                <select value={expiry} onChange={(e) => setExpiry(e.target.value)} className="rounded-md border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-50 outline-none focus:border-blue-500">
                                    {EXPIRIES.map((expo) => <option key={expo} value={expo}>{expo}</option>)}
                                </select>
                            </div>
                        </div>

                        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                            <div className="rounded-lg bg-slate-800 p-3">
                                <div className="text-xs text-slate-400">Spot</div>
                                <div className="text-lg font-bold">{formatNumber(data.spot)}</div>
                            </div>
                            <div className="rounded-lg bg-slate-800 p-3">
                                <div className="text-xs text-slate-400">Change</div>
                                <div className={`text-lg font-bold ${data.change >= 0 ? 'text-emerald-300' : 'text-rose-400'}`}>
                                    {data.change >= 0 ? '+' : ''}{formatNumber(data.change)} ({data.changePct >= 0 ? '+' : ''}{formatNumber(data.changePct)}%)
                                </div>
                            </div>
                            <div className="rounded-lg bg-slate-800 p-3">
                                <div className="text-xs text-slate-400">IV</div>
                                <div className="text-lg font-bold">{formatNumber(data.iv)}%</div>
                            </div>
                            <div className="rounded-lg bg-slate-800 p-3">
                                <div className="text-xs text-slate-400">PCR</div>
                                <div className="text-lg font-bold">{formatNumber(data.pcr)}</div>
                            </div>
                        </div>
                    </div>

                    <div className="overflow-x-auto rounded-xl border border-slate-700 bg-slate-900/70 shadow-md">
                        <table className="w-full min-w-[900px] text-left text-xs">
                            <thead className="sticky top-0 bg-slate-950/92 text-slate-300">
                                <tr>
                                    <th className="p-2 text-right">OI</th>
                                    <th className="p-2 text-right">OI Δ</th>
                                    <th className="p-2 text-right">IV</th>
                                    <th className="p-2 text-right">LTP</th>
                                    <th className="p-2 text-center bg-slate-800">Strike</th>
                                    <th className="p-2 text-left">LTP</th>
                                    <th className="p-2 text-left">IV</th>
                                    <th className="p-2 text-left">OI Δ</th>
                                    <th className="p-2 text-left">OI</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedChain.map((row) => {
                                    const isATM = row.strike === atmStrike;
                                    const rowShrink = isATM ? "bg-amber-500/15" : "hover:bg-slate-800/70";

                                    const formatDelta = (val) => {
                                        const cls = val >= 0 ? "text-emerald-300" : "text-rose-400";
                                        return <span className={cls}>{val >= 0 ? '+' : ''}{formatNumber(val)}%</span>;
                                    };

                                    return (
                                        <tr key={row.strike} className={rowShrink}>
                                            <td className="p-2 text-right text-slate-200">{row.call.oi}</td>
                                            <td className="p-2 text-right">{formatDelta(row.call.oiChange)}</td>
                                            <td className="p-2 text-right">{formatNumber(row.call.iv)}</td>
                                            <td className="p-2 text-right font-semibold text-sky-300">{formatNumber(row.call.ltp)}</td>

                                            <td className="p-2 text-center bg-slate-800">
                                                <div className="text-sm font-semibold">{row.strike}</div>
                                                <span className="text-[10px] text-slate-400">PCR {row.pcr}</span>
                                                {isATM && <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-slate-100/10 px-2 py-0.5 text-[10px] text-amber-200">ATM</div>}
                                            </td>

                                            <td className="p-2 text-left font-semibold text-sky-200">{formatNumber(row.put.ltp)}</td>
                                            <td className="p-2 text-left">{formatNumber(row.put.iv)}</td>
                                            <td className="p-2 text-left">{formatDelta(row.put.oiChange)}</td>
                                            <td className="p-2 text-left text-slate-200">{row.put.oi}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>

                <aside className="space-y-4">
                    <div className="rounded-xl border border-emerald-500/20 bg-slate-900/70 p-4 shadow-md">
                        <div className="mb-3 flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-emerald-300">Order Ticket</h3>
                            <span className="text-xs text-slate-400">Margin 5%</span>
                        </div>
                        <div className="space-y-2">
                            <div className="rounded-lg bg-slate-800 p-3">
                                <div className="mb-1 text-xs text-slate-400">Action</div>
                                <div className="flex gap-2">
                                    {['Buy', 'Sell'].map((sideOption) => (
                                        <button
                                            key={sideOption}
                                            onClick={() => setSide(sideOption)}
                                            className={`w-1/2 rounded-md px-2 py-1 text-xs font-semibold ${side === sideOption ? (side === 'Buy' ? 'bg-emerald-500/90 text-slate-900' : 'bg-rose-500/90 text-slate-900') : 'bg-slate-700 text-slate-200 hover:bg-slate-600'}`}
                                        >{sideOption}</button>
                                    ))}
                                </div>
                            </div>

                            <div className="rounded-lg bg-slate-800 p-3">
                                <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
                                    <label className="space-y-1">
                                        <div>Order Type</div>
                                        <select value={orderType} onChange={(e) => setOrderType(e.target.value)} className="w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1 text-sm text-slate-200 outline-none">
                                            <option>Market</option>
                                            <option>Limit</option>
                                            <option>SL-M</option>
                                            <option>SL</option>
                                        </select>
                                    </label>
                                    <label className="space-y-1">
                                        <div>Qty</div>
                                        <input type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value) || 1)} className="w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-1 text-sm outline-none" />
                                    </label>
                                </div>
                            </div>

                            <div className="rounded-lg bg-slate-800 p-3 space-y-2">
                                <label className="text-xs text-slate-400">Price</label>
                                <input type="number" min={0} value={price} onChange={(e) => setPrice(Number(e.target.value))} placeholder="Enter limit price" className="w-full rounded-md border border-slate-600 bg-slate-900 px-2 py-2 text-sm outline-none" />
                                <p className="text-xs text-slate-400">Market order will execute at best available price when price is empty.</p>
                            </div>

                            <button className={`w-full rounded-lg px-3 py-2 text-sm font-semibold ${side === 'Buy' ? 'bg-emerald-500 text-slate-900 hover:brightness-110' : 'bg-rose-500 text-slate-900 hover:brightness-110'}`}>Place {side} Order</button>
                        </div>
                    </div>

                    <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4 shadow-md">
                        <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Depth Snapshot</h4>
                        <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                            <div className="rounded-md bg-slate-800 p-2"><span className="text-slate-300">Spot</span><div className="font-semibold text-white">{formatNumber(data.spot)}</div></div>
                            <div className="rounded-md bg-slate-800 p-2"><span className="text-slate-300">Max Pain</span><div className="font-semibold text-white">{data.maxPain}</div></div>
                            <div className="rounded-md bg-slate-800 p-2"><span className="text-slate-300">VIX</span><div className="font-semibold text-white">{formatNumber(data.vix)}%</div></div>
                            <div className="rounded-md bg-slate-800 p-2"><span className="text-slate-300">Avg IV</span><div className="font-semibold text-white">{formatNumber(data.iv)}%</div></div>
                        </div>
                        <div className="mt-3 rounded-md bg-slate-800 p-3 text-[11px] text-slate-300">
                            <div className="inline-flex items-center gap-1"><TrendingUp size={12} className="text-emerald-300" /> Call buildup: {data.chain.reduce((acc, row) => acc + row.call.oi, 0).toFixed(1)}</div>
                            <div className="inline-flex items-center gap-1 mt-1"><TrendingDown size={12} className="text-rose-300" /> Put buildup: {data.chain.reduce((acc, row) => acc + row.put.oi, 0).toFixed(1)}</div>
                        </div>
                    </div>
                </aside>
            </section>

            <footer className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 text-xs text-slate-400">
                <p>The table is sorted by strike price by default. Click on any header to add interactive sorting in the next iteration.</p>
            </footer>
        </div>
    );
}
