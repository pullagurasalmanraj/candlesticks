import React, { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Search, Upload, Calendar, Cpu } from "lucide-react";

export default function TransformerPredictor() {
    const [symbol, setSymbol] = useState("");
    const [filteredSymbols, setFilteredSymbols] = useState([]);
    const [start, setStart] = useState("");
    const [end, setEnd] = useState("");
    const [use100Years, setUse100Years] = useState(false);
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [showDropdown, setShowDropdown] = useState(false);

    // Server-side instrument search (debounced)
    useEffect(() => {
        const q = symbol.trim();
        if (q.length < 2) {
            setFilteredSymbols([]);
            setShowDropdown(false);
            return;
        }

        const controller = new AbortController();
        const timer = setTimeout(async () => {
            try {
                const res = await axios.get("/api/instruments", {
                    params: { q },
                    signal: controller.signal,
                });
                const items = Array.isArray(res?.data?.instruments)
                    ? res.data.instruments
                    : [];
                setFilteredSymbols(items.slice(0, 10));
                setShowDropdown(true);
            } catch (e) {
                if (e.name !== "CanceledError" && e.name !== "AbortError") {
                    console.error("Error loading instruments:", e);
                }
                setFilteredSymbols([]);
                setShowDropdown(false);
            }
        }, 180);

        return () => {
            clearTimeout(timer);
            controller.abort();
        };
    }, [symbol]);

    // 🧠 Dropdown auto-close on outside click
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (!e.target.closest(".dropdown-area")) setShowDropdown(false);
        };
        document.addEventListener("click", handleClickOutside);
        return () => document.removeEventListener("click", handleClickOutside);
    }, []);

    const handleSelectSymbol = (selected) => {
        setSymbol(selected);
        setShowDropdown(false);
    };

    // 📤 Submit Prediction Request
    const handleSubmit = async (e) => {
        e.preventDefault();
        if (loading) return;
        setLoading(true);
        setResult(null);

        try {
            let res;

            if (file) {
                // If Excel or CSV uploaded
                const formData = new FormData();
                formData.append("file", file);
                formData.append("symbol", symbol || "CUSTOM");

                res = await axios.post("/api/predict-transformer", formData, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
            } else {
                // JSON body (Yahoo Finance)
                const payload = {
                    symbol,
                    start: use100Years ? "1925-01-01" : start,
                    end: use100Years
                        ? new Date().toISOString().slice(0, 10)
                        : end,
                };
                res = await axios.post("/api/predict-transformer", payload);
            }

            setResult(res.data);
        } catch (error) {
            console.error(error);
            setResult({ error: error.response?.data?.error || "Prediction failed" });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div
            className="min-h-screen flex flex-col items-center justify-center px-4 py-10 transition-colors"
            style={{ background: "transparent", color: "var(--text-primary)" }}
        >
            <motion.div
                initial={{ opacity: 0, y: 25 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="w-full max-w-2xl p-8 border"
                style={{
                    borderRadius: "var(--card-radius)", background: "var(--surface-glass)",
                    borderColor: "var(--border-color)", boxShadow: "var(--shadow-card)",
                    backdropFilter: "blur(20px) saturate(140%)",
                }}
            >
                <h2
                    className="text-3xl font-bold flex items-center gap-2 mb-6"
                    style={{ color: "var(--accent-blue)" }}
                >
                    <Cpu size={28} /> Transformer Stock Predictor
                </h2>

                <form onSubmit={handleSubmit} className="space-y-5">
                    {/* 🔍 Stock Search */}
                    <div className="relative dropdown-area">
                        <label className="block font-semibold mb-1">Stock Symbol</label>
                        <div
                            className="flex items-center gap-2 px-3 py-2 rounded-lg border"
                            style={{ borderColor: "var(--border-color)", background: "var(--bg-tertiary)" }}
                        >
                            <Search size={18} className="opacity-70" />
                            <input
                                type="text"
                                placeholder="Search stock (e.g. INFY, RELIANCE)"
                                value={symbol}
                                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                                className="w-full outline-none bg-transparent"
                                style={{ color: "var(--text-primary)" }}
                            />
                        </div>

                        {showDropdown && filteredSymbols.length > 0 && (
                            <div
                                className="absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-lg shadow-lg border"
                                style={{ background: "var(--bg-secondary)", borderColor: "var(--border-color)", boxShadow: "var(--shadow-card)" }}
                            >
                                {filteredSymbols.map((item) => (
                                    <button
                                        key={item.symbol}
                                        type="button"
                                        onClick={() => handleSelectSymbol(item.symbol)}
                                        className="theme-hover w-full text-left px-4 py-2 text-sm"
                                        style={{ color: "var(--text-primary)" }}
                                    >
                                        {item.symbol} – {item.name}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* 📅 Date and 100-Year Toggle */}
                    <div className="flex items-center gap-3">
                        <input
                            type="checkbox"
                            checked={use100Years}
                            onChange={() => setUse100Years(!use100Years)}
                        />
                        <span className="text-sm font-medium">
                            Fetch 100 Years of Data (1925 - Present)
                        </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block font-semibold mb-1">Start Date</label>
                            <div className="flex items-center gap-2">
                                <Calendar size={18} />
                                <input
                                    type="date"
                                    value={start}
                                    onChange={(e) => setStart(e.target.value)}
                                    disabled={use100Years}
                                    className="w-full p-2 rounded-lg border"
                                    style={{ borderColor: "var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block font-semibold mb-1">End Date</label>
                            <div className="flex items-center gap-2">
                                <Calendar size={18} />
                                <input
                                    type="date"
                                    value={end}
                                    onChange={(e) => setEnd(e.target.value)}
                                    disabled={use100Years}
                                    className="w-full p-2 rounded-lg border"
                                    style={{ borderColor: "var(--border-color)", background: "var(--bg-tertiary)", color: "var(--text-primary)" }}
                                />
                            </div>
                        </div>
                    </div>

                    {/* 📂 Excel Upload */}
                    <div>
                        <label className="block font-semibold mb-1">
                            Upload Excel (optional)
                        </label>
                        <div
                            className="theme-hover flex items-center gap-3 p-3 rounded-lg border cursor-pointer"
                            style={{ borderColor: "var(--border-color)", background: "var(--bg-tertiary)" }}
                            onClick={() => document.getElementById("fileInput").click()}
                        >
                            <Upload size={20} />
                            <span>{file ? file.name : "Click to upload XLSX or CSV"}</span>
                        </div>
                        <input
                            id="fileInput"
                            type="file"
                            accept=".xlsx,.csv"
                            className="hidden"
                            onChange={(e) => {
                                const selected = e.target.files[0];
                                setFile(selected);
                                if (selected) setSymbol("CUSTOM");
                            }}
                        />
                    </div>

                    {/* 🔮 Predict Button */}
                    <motion.button
                        whileTap={{ scale: 0.97 }}
                        disabled={loading}
                        className={`w-full py-3 rounded-xl font-semibold flex justify-center items-center gap-2 transition-all ${loading ? "opacity-70 cursor-wait" : ""}`}
                        style={{ background: "var(--accent-gradient)", color: "var(--accent-contrast)", boxShadow: "var(--shadow-glow-blue)" }}
                    >
                        {loading ? "Predicting..." : "🔮 Predict with Transformer"}
                    </motion.button>
                </form>

                {/* 🧠 Result */}
                {result && (
                    <motion.div
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4 }}
                        className="mt-8 p-6 rounded-2xl shadow-2xl border overflow-hidden"
                        style={{ background: "linear-gradient(145deg, var(--bg-secondary), var(--bg-tertiary))", borderColor: "var(--accent-blue)" }}
                    >
                        {result.error ? (
                            <div className="text-center text-red-500 font-semibold">
                                ❌ Prediction Failed: {result.error}
                            </div>
                        ) : (
                            <>
                                <h3
                                    className="text-2xl font-extrabold mb-4 text-center"
                                    style={{ color: "var(--accent-blue)" }}
                                >
                                    🚀 Prediction Summary
                                </h3>
                                <p className="text-center text-lg font-semibold">
                                    Symbol:{" "}
                                    <span style={{ color: "var(--accent-blue)" }}>
                                        {result.symbol || "CUSTOM"}
                                    </span>
                                </p>
                                <div className="flex flex-col items-center mt-4">
                                    <h4 className="uppercase text-xs opacity-60">
                                        Predicted Open Price
                                    </h4>
                                    <motion.div
                                        initial={{ scale: 0.8 }}
                                        animate={{ scale: 1 }}
                                        transition={{ type: "spring", stiffness: 120 }}
                                        className="relative mt-2"
                                    >
                                        <span className="text-5xl font-extrabold" style={{ color: "var(--accent-up)" }}>
                                            ₹{Number(result.predicted_open).toFixed(2)}
                                        </span>
                                    </motion.div>
                                </div>

                                <p className="text-center text-sm mt-4 opacity-75">
                                    📊 Data Processed:{" "}
                                    <span className="font-semibold" style={{ color: "var(--accent-blue)" }}>
                                        {result.rows_used || "N/A"} rows
                                    </span>
                                </p>

                                <p className="text-center text-xs mt-2 italic opacity-70">
                                    Model: Transformer Neural Network • Confidence Level: High ⚡
                                </p>

                                <div className="flex justify-center mt-6">
                                    <motion.button
                                        whileHover={{ scale: 1.05 }}
                                        whileTap={{ scale: 0.95 }}
                                        onClick={() => setResult(null)}
                                        className="px-6 py-2 rounded-lg font-medium shadow-md transition-all"
                                        style={{ background: "var(--accent-gradient)", color: "var(--accent-contrast)", boxShadow: "var(--shadow-glow-blue)" }}
                                    >
                                        🔄 New Prediction
                                    </motion.button>
                                </div>
                            </>
                        )}
                    </motion.div>
                )}
            </motion.div>
        </div>
    );
}
