import React, { useState, useEffect } from "react";
import axios from "axios";
import { motion } from "framer-motion";
import { Search, Upload, Calendar, Cpu } from "lucide-react";
import { useTheme } from "../context/ThemeContext";

export default function TransformerPredictor() {
    const { theme } = useTheme();
    const isLight = theme === "light";

    const [symbol, setSymbol] = useState("");
    const [filteredSymbols, setFilteredSymbols] = useState([]);
    const [allSymbols, setAllSymbols] = useState([]);
    const [start, setStart] = useState("");
    const [end, setEnd] = useState("");
    const [use100Years, setUse100Years] = useState(false);
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [showDropdown, setShowDropdown] = useState(false);

    // 🔁 Fetch instrument list on load
    useEffect(() => {
        const fetchInstruments = async () => {
            try {
                const res = await axios.get("/api/instruments");
                setAllSymbols(res.data.instruments || []);
            } catch (e) {
                console.error("Error loading instruments:", e);
            }
        };
        fetchInstruments();
    }, []);

    // 🔍 Fuzzy search logic
    useEffect(() => {
        if (symbol.length > 0) {
            const filtered = allSymbols.filter((s) =>
                s.symbol.toLowerCase().includes(symbol.toLowerCase())
            );
            setFilteredSymbols(filtered.slice(0, 10)); // limit to 10 results
            setShowDropdown(true);
        } else {
            setShowDropdown(false);
        }
    }, [symbol, allSymbols]);

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
            className={`min-h-screen flex flex-col items-center justify-center px-4 py-10 transition-colors ${isLight
                ? "bg-gradient-to-br from-white via-blue-50 to-gray-100 text-gray-800"
                : "bg-gradient-to-br from-[#0b0f19] via-[#111827] to-[#1e293b] text-gray-100"
                }`}
        >
            <motion.div
                initial={{ opacity: 0, y: 25 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className={`w-full max-w-2xl p-8 rounded-2xl shadow-xl border ${isLight
                    ? "bg-white border-gray-200"
                    : "bg-gray-900/60 border-gray-700"
                    }`}
            >
                <h2
                    className={`text-3xl font-bold flex items-center gap-2 mb-6 ${isLight ? "text-indigo-700" : "text-indigo-400"
                        }`}
                >
                    <Cpu size={28} /> Transformer Stock Predictor
                </h2>

                <form onSubmit={handleSubmit} className="space-y-5">
                    {/* 🔍 Stock Search */}
                    <div className="relative dropdown-area">
                        <label className="block font-semibold mb-1">Stock Symbol</label>
                        <div
                            className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${isLight
                                ? "border-gray-300 bg-white"
                                : "border-gray-700 bg-gray-800"
                                }`}
                        >
                            <Search size={18} className="opacity-70" />
                            <input
                                type="text"
                                placeholder="Search stock (e.g. INFY, RELIANCE)"
                                value={symbol}
                                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                                className={`w-full outline-none bg-transparent ${isLight ? "text-gray-800" : "text-gray-100"
                                    }`}
                            />
                        </div>

                        {showDropdown && filteredSymbols.length > 0 && (
                            <div
                                className={`absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-lg shadow-lg border ${isLight
                                    ? "bg-white border-gray-200"
                                    : "bg-gray-800 border-gray-700"
                                    }`}
                            >
                                {filteredSymbols.map((item) => (
                                    <button
                                        key={item.symbol}
                                        type="button"
                                        onClick={() => handleSelectSymbol(item.symbol)}
                                        className={`w-full text-left px-4 py-2 text-sm ${isLight
                                            ? "hover:bg-blue-100 text-gray-800"
                                            : "hover:bg-gray-700 text-gray-100"
                                            }`}
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
                                    className={`w-full p-2 rounded-lg border ${isLight
                                        ? "border-gray-300 bg-white"
                                        : "border-gray-700 bg-gray-800"
                                        }`}
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
                                    className={`w-full p-2 rounded-lg border ${isLight
                                        ? "border-gray-300 bg-white"
                                        : "border-gray-700 bg-gray-800"
                                        }`}
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
                            className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer ${isLight
                                ? "border-gray-300 hover:bg-gray-100"
                                : "border-gray-700 hover:bg-gray-800"
                                }`}
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
                        className={`w-full py-3 rounded-xl font-semibold flex justify-center items-center gap-2 transition-all ${loading
                            ? "opacity-70 cursor-wait"
                            : isLight
                                ? "bg-indigo-600 hover:bg-indigo-700 text-white"
                                : "bg-indigo-500 hover:bg-indigo-400 text-white"
                            }`}
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
                        className={`mt-8 p-6 rounded-2xl shadow-2xl border overflow-hidden ${isLight
                            ? "bg-gradient-to-br from-white via-indigo-50 to-gray-100 border-indigo-200"
                            : "bg-gradient-to-br from-gray-900 via-gray-800 to-gray-700 border-indigo-700"
                            }`}
                    >
                        {result.error ? (
                            <div className="text-center text-red-500 font-semibold">
                                ❌ Prediction Failed: {result.error}
                            </div>
                        ) : (
                            <>
                                <h3
                                    className={`text-2xl font-extrabold mb-4 text-center ${isLight ? "text-indigo-700" : "text-indigo-400"
                                        }`}
                                >
                                    🚀 Prediction Summary
                                </h3>
                                <p className="text-center text-lg font-semibold">
                                    Symbol:{" "}
                                    <span className="text-indigo-500">
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
                                        <span className="text-5xl font-extrabold text-green-500">
                                            ₹{Number(result.predicted_open).toFixed(2)}
                                        </span>
                                    </motion.div>
                                </div>

                                <p className="text-center text-sm mt-4 opacity-75">
                                    📊 Data Processed:{" "}
                                    <span className="font-semibold text-indigo-500">
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
                                        className={`px-6 py-2 rounded-lg font-medium shadow-md transition-all ${isLight
                                            ? "bg-indigo-600 hover:bg-indigo-700 text-white"
                                            : "bg-indigo-500 hover:bg-indigo-400 text-white"
                                            }`}
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
