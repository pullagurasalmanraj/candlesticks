import { useState } from "react";
import { useTheme } from "../context/ThemeContext";
import { Activity } from "lucide-react";

/* ---------------- MOCK OPTION CHAIN DATA ---------------- */

const MOCK_CHAIN = {
    symbol: "NIFTY",
    spot: 26146.55,
    vix: 9.19,
    maxPain: 26150,
    chain: [
        {
            strike: 26050,
            pcr: 5.7,
            call: { ltp: 152.0, oi: 12.7, oiChange: -6.0, iv: 10.3 },
            put: { ltp: 36.4, oi: 72.9, oiChange: 25.0, iv: 10.3 }
        },
        {
            strike: 26100,
            pcr: 2.03,
            call: { ltp: 117.6, oi: 51.3, oiChange: 23.8, iv: 11.4 },
            put: { ltp: 51.1, oi: 104.4, oiChange: 31.0, iv: 11.4 }
        },
        {
            strike: 26150,
            pcr: 1.0,
            call: { ltp: 86.4, oi: 58.5, oiChange: 59.6, iv: 12.1 },
            put: { ltp: 70.2, oi: 58.7, oiChange: 74.5, iv: 12.1 }
        },
        {
            strike: 26200,
            pcr: 0.42,
            call: { ltp: 61.5, oi: 123.5, oiChange: 95.1, iv: 12.1 },
            put: { ltp: 94.6, oi: 51.7, oiChange: 27.2, iv: 12.1 }
        }
    ]
};

/* ---------------- COMPONENT ---------------- */

export default function OptionsTrading() {
    const { theme } = useTheme();
    const isLight = theme === "light";

    const [symbol, setSymbol] = useState("NIFTY");
    const data = MOCK_CHAIN;

    return (
        <div className="p-6 space-y-6">

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold">Options Trading</h1>
                    <p className="text-xs text-slate-400">
                        Option Chain View
                    </p>
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400">
                    <Activity size={14} />
                    NSE Derivatives
                </div>
            </div>


            {/* Symbol Selector */}
            <div className="flex gap-3 text-sm">
                {["NIFTY", "BANKNIFTY", "FINNIFTY"].map(s => (
                    <button
                        key={s}
                        onClick={() => setSymbol(s)}
                        className={`px-3 py-1 rounded-md border ${symbol === s ? "bg-blue-600 text-white" : ""
                            }`}
                    >
                        {s}
                    </button>
                ))}
            </div>

            {/* Market Info */}
            <div
                className={`rounded-xl border p-4 ${isLight ? "bg-white" : "bg-slate-900 border-slate-800"
                    }`}
            >
                <div className="flex gap-6 text-sm">
                    <span>Spot: <b>{data.spot}</b></span>
                    <span>VIX: <b>{data.vix}</b></span>
                    <span>Max Pain: <b>{data.maxPain}</b></span>
                </div>
            </div>

            {/* Option Chain Table */}
            <div className="overflow-auto rounded-xl border border-slate-800">
                <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-slate-900">
                        <tr>
                            <th className="p-2 text-left">OI</th>
                            <th className="p-2">OI Δ</th>
                            <th className="p-2">IV</th>
                            <th className="p-2">LTP</th>
                            <th className="p-2 bg-slate-800">STRIKE</th>
                            <th className="p-2">LTP</th>
                            <th className="p-2">IV</th>
                            <th className="p-2">OI Δ</th>
                            <th className="p-2 text-right">OI</th>
                        </tr>
                    </thead>

                    <tbody>
                        {data.chain.map(row => {
                            const isATM = Math.abs(row.strike - data.spot) < 30;

                            return (
                                <tr
                                    key={row.strike}
                                    className={isATM ? "bg-yellow-500/10" : ""}
                                >
                                    {/* CALLS */}
                                    <td className="p-2">{row.call.oi}</td>
                                    <td className="p-2 text-green-400">{row.call.oiChange}%</td>
                                    <td className="p-2">{row.call.iv}</td>
                                    <td className="p-2 font-medium">{row.call.ltp}</td>

                                    {/* STRIKE */}
                                    <td className="p-2 bg-slate-800 font-semibold text-center">
                                        {row.strike}
                                        <div className="text-[10px] text-slate-400">
                                            PCR {row.pcr}
                                        </div>
                                    </td>

                                    {/* PUTS */}
                                    <td className="p-2 font-medium">{row.put.ltp}</td>
                                    <td className="p-2">{row.put.iv}</td>
                                    <td className="p-2 text-green-400">{row.put.oiChange}%</td>
                                    <td className="p-2 text-right">{row.put.oi}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

        </div>
    );
}
