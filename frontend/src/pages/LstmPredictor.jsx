import { Loader2, BarChart3, Wand2, Sparkles } from "lucide-react";

import React, { useState, useEffect, useRef } from "react";
import { useTheme } from "../context/ThemeContext";







export default function MLTrainingPage() {
    const { theme } = useTheme();
    const isLight = theme === "light";

    const [symbol, setSymbol] = useState("");
    const [filtered, setFiltered] = useState([]);
    const [timeframe, setTimeframe] = useState("5m");
    const [task] = useState("classification");
    const [trainSplit] = useState(0.8);

    const [paperLoading, setPaperLoading] = useState(false);
    const [paperResult, setPaperResult] = useState(null);

    const [riskPct, setRiskPct] = useState(1);       // 1%
    const [rrRatio, setRrRatio] = useState(2.5);     // 1:2.5
    const [threshold, setThreshold] = useState(0.7);
    const [compareLoading, setCompareLoading] = useState(false);
    const [compareResults, setCompareResults] = useState(null);

    const [paperProgress, setPaperProgress] = useState("");

    const [paperPercent, setPaperPercent] = useState(0);



    const [loading, setLoading] = useState(false);

    const [outcomeLoading, setOutcomeLoading] = useState(false);
    const [outcomeResult, setOutcomeResult] = useState(null);

    // 🔴 LIVE ENGINE STATE (BACKEND DRIVEN)
    const [liveMode, setLiveMode] = useState(false);
    const [predictLoading, setPredictLoading] = useState(false);
    const [engineStatus, setEngineStatus] = useState("IDLE");
    const [tradeState, setTradeState] = useState(null);

    const [marginPerShare, setMarginPerShare] = useState(21.68);

    const didFetchRef = useRef(false);

    const [equityRunId, setEquityRunId] = useState(null);
    const [equityCurve, setEquityCurve] = useState([]);
    const [equityLoading, setEquityLoading] = useState(false);


    const [convertLoading, setConvertLoading] = useState(false);
    const [convertMessage, setConvertMessage] = useState("");

    const [labelLoading, setLabelLoading] = useState(false);
    const [labelResult, setLabelResult] = useState(null);
    const [lookahead, setLookahead] = useState(20);
    const [windowSize, setWindowSize] = useState(30);

    const [ruleStats, setRuleStats] = useState(null);
    const [ruleStatsLoading, setRuleStatsLoading] = useState(false);
    const [searchResults, setSearchResults] = useState([]);
    const [trainResults, setTrainResults] = useState(null);

    const [search, setSearch] = useState("");

    const [searching, setSearching] = useState(false);

    const panelStyle = {
        backgroundColor: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: "12px",
    };



    useEffect(() => {
        if (!search || search.length < 2) {
            setSearchResults([]);
            didFetchRef.current = false;
            return;
        }

        if (didFetchRef.current) return;
        didFetchRef.current = true;

        const controller = new AbortController();
        const t = setTimeout(async () => {
            try {
                setSearching(true);
                const res = await fetch(
                    `/api/instruments?q=${encodeURIComponent(search)}`,
                    { signal: controller.signal }
                );
                const data = await res.json();

                setSearchResults(
                    Array.isArray(data.instruments) ? data.instruments : []
                );
            } catch (e) {
                if (e.name !== "AbortError") {
                    console.error(e);
                    setSearchResults([]);
                }
            } finally {
                setSearching(false);
                didFetchRef.current = false;
            }
        }, 200);

        return () => {
            controller.abort();
            clearTimeout(t);
        };
    }, [search]);




    const handleSearch = (value) => {
        const v = value.toUpperCase();
        setSymbol(v);
        setSearch(v);
    };

    const startFakeProgress = () => {
        setPaperPercent(5);

        let p = 5;
        const interval = setInterval(() => {
            p += Math.random() * 7;   // slow increase
            if (p >= 90) {
                p = 90;               // never reach 100 until backend finishes
                clearInterval(interval);
            }
            setPaperPercent(Math.floor(p));
        }, 700);

        return interval;
    };



    // 🔧 MODIFIED: tasks are now logical only (no endpoints)
    const TRAIN_TASKS = [
        {
            key: "edge_gate",
            label: "Edge Gate (Trade Permission)"
        },
        {
            key: "context_expectancy",
            label: "Context Expectancy (R Regression)"
        },
        {
            key: "edge_decay",
            label: "Edge Decay (Edge Velocity)"
        }
    ];


    // --------------------------------------------------
    // Train Model Pipeline
    // --------------------------------------------------
    const handleTrain = async () => {
        if (!symbol) {
            alert("Select stock");
            return;
        }

        setLoading(true);
        setTrainResults(null);

        try {
            const res = await fetch("/api/train-pipeline", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe })
            });

            const data = await res.json();
            console.log("TRAIN PIPELINE RESPONSE:", data);

            if (data.status !== "SUCCESS") {
                throw new Error("Training failed");
            }

            const results = [];

            // =====================================
            // RULE-BASED MODELS (EDGE GATE + CONTEXT + DECAY)
            // =====================================
            Object.entries(data.rules || {}).forEach(([ruleName, ruleModels]) => {

                // EDGE GATE
                if (ruleModels.edge_gate) {
                    results.push({
                        key: `edge_gate_${ruleName}`,
                        type: "edge_gate",
                        label: `${ruleName} · Edge Gate`,
                        status: ruleModels.edge_gate.status,
                        auc: ruleModels.edge_gate.auc,
                        recommended_threshold: ruleModels.edge_gate.recommended_threshold,
                        model_path: ruleModels.edge_gate.model_path,
                        error: ruleModels.edge_gate.reason
                    });
                }

                // CONTEXT EXPECTANCY (RULE-LOCAL)
                if (ruleModels.context_expectancy) {
                    results.push({
                        key: `context_expectancy_${ruleName}`,
                        type: "context_expectancy",
                        label: `${ruleName} · Context Expectancy`,
                        status: ruleModels.context_expectancy.status,
                        rmse: ruleModels.context_expectancy.rmse,
                        model_path: ruleModels.context_expectancy.model_path,
                        error: ruleModels.context_expectancy.reason
                    });
                }

                // EDGE DECAY (RULE-LOCAL)
                if (ruleModels.edge_decay) {
                    results.push({
                        key: `edge_decay_${ruleName}`,
                        type: "edge_decay",
                        label: `${ruleName} · Edge Decay`,
                        status: ruleModels.edge_decay.status,
                        rmse: ruleModels.edge_decay.rmse,
                        model_path: ruleModels.edge_decay.model_path,
                        error: ruleModels.edge_decay.reason
                    });
                }
            });

            console.log("NORMALIZED RESULTS:", results);
            setTrainResults(results);

        } catch (e) {
            setTrainResults([
                {
                    key: "PIPELINE_ERROR",
                    type: "error",
                    label: "Training Pipeline",
                    status: "ERROR",
                    error: e.message
                }
            ]);
        } finally {
            setLoading(false);
        }
    };


    // --------------------------------------------------
    // Convert Ticks → Candles
    // --------------------------------------------------
    const handleConvertTicks = async () => {
        if (!symbol) return alert("Select stock");

        setConvertLoading(true);
        setConvertMessage("");

        try {
            const mapRes = await fetch(`/api/symbol-feedkey?symbol=${symbol}`);
            const mapData = await mapRes.json();

            const res = await fetch("/api/start-live-conversion", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol,
                    feed_key: mapData.feed_key
                })
            });

            const json = await res.json();

            if (json.status === "STARTED") {
                setConvertMessage(`✅ Live conversion started\nSymbol: ${symbol}`);
            } else if (json.status === "ALREADY_RUNNING") {
                setConvertMessage(`ℹ️ Conversion already running for ${symbol}`);
            } else {
                setConvertMessage(JSON.stringify(json, null, 2));
            }
        } catch (e) {
            setConvertMessage("❌ Error:\n" + e.message);
        }

        setConvertLoading(false);
    };

    const handleOfflineLabeling = async () => {
        if (!symbol) return alert("Select stock first");

        setLabelLoading(true);
        setLabelResult(null);

        try {
            const res = await fetch("/api/offline/label-market-context", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol,
                    timeframe,
                    windowSize
                })

            });

            const data = await res.json();
            setLabelResult(data);

            // OPTIONAL: after labeling, fetch latest rule stats
            // fetchRuleStats();

        } catch (e) {
            setLabelResult({ error: e.message });
        }

        setLabelLoading(false);
    };



    const handleOfflineSuccess = async () => {
        console.log("👉 handleOfflineSuccess CLICKED");

        if (!symbol) {
            alert("Select stock first");
            return;
        }

        setOutcomeLoading(true);
        setOutcomeResult({
            status: "RUNNING",
            message: "Computing strategy outcomes… this may take a few minutes"
        });

        try {
            const res = await fetch("/api/offline/calc-strategy-outcomes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol,
                    timeframe
                    // ✅ NO lookahead
                    // optional later: from_date, to_date
                })
            });

            let data;
            try {
                data = await res.json();
            } catch {
                throw new Error("Server did not return JSON");
            }

            if (!res.ok) {
                setOutcomeResult({
                    error: data.error || "Computation failed",
                    details: data
                });
                return;
            }

            setOutcomeResult(data);

        } catch (e) {
            console.error(e);
            setOutcomeResult({
                error: "Request failed",
                message: e.message
            });
        } finally {
            setOutcomeLoading(false);
        }
    };



    const fetchRuleStats = async () => {
        if (!symbol) return;

        setRuleStatsLoading(true);

        try {
            const res = await fetch(
                `/api/market-context/rule-stats?symbol=${symbol}&timeframe=${timeframe}`
            );

            if (!res.ok) {
                throw new Error(`Rule stats failed: ${res.status}`);
            }

            const data = await res.json();
            setRuleStats(data);
        } catch (e) {
            console.error("Rule stats error:", e);
            setRuleStats(null);
        } finally {
            setRuleStatsLoading(false);
        }
    };


    // --------------------------------------------------
    // Paper Trade Simulation (ONE SHOT)
    const runPaperTrading = async () => {
        if (!symbol) return alert("Select stock first");
        if (!trainResults?.model_run_id) return alert("Train model first");

        setPaperLoading(true);
        setPaperResult(null);
        setEquityCurve([]);
        setPaperProgress("Initializing paper trading engine…");

        const progressTimer = startFakeProgress();

        try {
            setPaperProgress("Running leverage-based trade simulation…");

            const res = await fetch("/api/paper-trade/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol,
                    timeframe,
                    model_run_id: trainResults.model_run_id,
                    margin_per_share: marginPerShare,
                    starting_capital: 10000,
                    risk_pct: riskPct,
                    rr_ratio: rrRatio,
                    threshold
                })
            });

            const data = await res.json();

            if (!res.ok) {
                clearInterval(progressTimer);
                setPaperPercent(0);
                setPaperResult({ error: data.error });
                return;
            }

            setPaperProgress("Saving trades & computing equity…");
            setPaperPercent(95);

            setPaperResult(data);

            if (data.paper_trade_run_id) {
                await fetchEquityCurve(data.paper_trade_run_id);
            }

            setPaperProgress("Completed");
            setPaperPercent(100);

        } catch (e) {
            setPaperResult({ error: e.message });
            setPaperPercent(0);
        } finally {
            clearInterval(progressTimer);
            setPaperLoading(false);
        }
    };


    const fetchEquityCurve = async (runId) => {
        if (!runId) return;

        setEquityLoading(true);
        setEquityCurve([]);

        try {
            const res = await fetch(
                `/api/paper-trade/equity-curve?run_id=${runId}`
            );

            const data = await res.json();
            setEquityCurve(data.curve || []);
        } catch (e) {
            console.error("Equity curve error:", e);
        } finally {
            setEquityLoading(false);
        }
    };

    const compareThresholds = async () => {
        if (!symbol || !trainResults?.model_run_id) {
            alert("Train model first");
            return;
        }

        setCompareLoading(true);
        setCompareResults(null);

        try {
            const res = await fetch("/api/paper-trade/compare-thresholds", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol,
                    timeframe,
                    model_run_id: trainResults.model_run_id,
                    starting_capital: 10000,
                    risk_pct: riskPct,
                    rr_ratio: rrRatio,
                    thresholds: [0.6, 0.7]
                })
            });

            const data = await res.json();
            setCompareResults(data);

        } catch (e) {
            console.error(e);
            setCompareResults({ error: e.message });
        } finally {
            setCompareLoading(false);
        }
    };


    return (
        <div
            className="w-full text-sm"
            style={{
                backgroundColor: "var(--bg-primary)",
                color: "var(--text-primary)"
            }}
        >
            <div
                className="w-full max-w-4xl mx-auto p-6 space-y-5"
                style={{
                    backgroundColor: "var(--bg-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "10px"
                }}
            >

                {/* HEADER */}
                <div className="flex items-center gap-2">
                    <BarChart3 size={18} />
                    <h1 className="text-lg font-semibold tracking-wide">
                        AI Trading Model Trainer
                    </h1>
                </div>

                {/* SEARCH INPUT */}
                <input
                    placeholder="Search stocks…"
                    value={search}
                    onChange={(e) => handleSearch(e.target.value)}
                    className="w-full h-11 px-3 rounded-md text-sm"
                    style={{
                        backgroundColor: "var(--bg-tertiary)",
                        border: "1px solid var(--border-color)",
                        color: "var(--text-primary)"
                    }}
                />


                {/* SEARCH RESULTS */}
                {searchResults.length > 0 && (
                    <ul
                        className="mt-1 max-h-60 overflow-y-auto rounded-md"
                        style={{
                            backgroundColor: "var(--bg-secondary)",
                            border: "1px solid var(--border-color)"
                        }}
                    >
                        {searchResults.map(inst => (
                            <li
                                key={inst.instrument_key}
                                onClick={() => {
                                    setSymbol(inst.symbol);
                                    setSearch(inst.symbol);
                                    setSearchResults([]);
                                }}
                                className="px-3 py-2 cursor-pointer"
                            >

                                <div className="text-sm font-medium">
                                    {inst.symbol}
                                </div>

                                <div
                                    className="text-xs"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    {inst.name} · {inst.segment}
                                </div>
                            </li>
                        ))}
                    </ul>
                )}




                {/* TIMEFRAME + TRAIN */}
                <div className="space-y-4 max-w-xl">

                    {/* TIMEFRAME SELECT */}
                    <select
                        className="w-full h-11 px-3 rounded-md text-sm"
                        style={{
                            backgroundColor: "var(--bg-tertiary)",
                            border: "1px solid var(--border-color)",
                            color: "var(--text-primary)"
                        }}
                        value={timeframe}
                        onChange={(e) => setTimeframe(e.target.value)}
                    >
                        {["1m", "3m", "5m", "15m", "30m", "1D"].map(tf => (
                            <option key={tf}>{tf}</option>
                        ))}
                    </select>

                    {/* TRAIN BUTTON */}
                    <button
                        type="button"
                        onClick={handleTrain}
                        disabled={loading}
                        className="h-11 px-6 rounded-md shadow-sm inline-flex items-center justify-center gap-2 text-sm font-medium"
                        style={{ backgroundColor: "var(--accent-up)", color: "#fff" }}
                    >
                        {loading ? (
                            <Loader2 className="animate-spin w-4 h-4" />
                        ) : (
                            <Wand2 className="w-4 h-4" />
                        )}
                        Train Models
                    </button>

                </div>

                {trainResults && (
                    <div className="mt-6 space-y-3 max-w-xl">
                        <div className="text-sm font-semibold tracking-wide">
                            Rule Intelligence
                        </div>

                        {trainResults.filter(r => r.type === "edge_gate").length === 0 && (
                            <div className="text-xs text-muted">
                                No rule-based models trained for this symbol.
                            </div>
                        )}

                        {trainResults
                            .filter(r => r.type === "edge_gate")
                            .sort((a, b) => (b.auc ?? 0) - (a.auc ?? 0))   // ⭐ optional but good
                            .map(result => {
                                const auc = result.auc ?? 0;
                                const statusColor =
                                    auc >= 0.6 ? "var(--accent-up)"
                                        : auc >= 0.55 ? "#f0ad4e"
                                            : "var(--accent-down)";

                                const statusLabel =
                                    auc >= 0.6 ? "ACTIVE"
                                        : auc >= 0.55 ? "WEAK"
                                            : "DISABLED";

                                return (
                                    <div
                                        key={result.key}
                                        className="flex justify-between items-center px-4 py-3 rounded-md text-sm"
                                        style={{
                                            backgroundColor: "var(--bg-tertiary)",
                                            border: "1px solid var(--border-color)"
                                        }}
                                    >
                                        <div>
                                            <div className="font-medium">
                                                {result.label.replace(" · Edge Gate", "")}
                                            </div>
                                            <div
                                                className="text-xs"
                                                style={{ color: "var(--text-secondary)" }}
                                            >
                                                AUC: {typeof result.auc === "number"
                                                    ? result.auc.toFixed(3)
                                                    : "—"}
                                            </div>
                                        </div>

                                        <div
                                            className="px-3 py-1 rounded-full text-[11px] font-semibold"
                                            style={{
                                                backgroundColor: `${statusColor}22`,
                                                color: statusColor
                                            }}
                                        >
                                            {statusLabel}
                                        </div>
                                    </div>
                                );
                            })}
                    </div>
                )}
                {trainResults && (
                    <div className="mt-8 space-y-3 max-w-xl">
                        <div className="text-sm font-semibold tracking-wide">
                            Market Context Models
                        </div>

                        {trainResults.filter(r =>
                            r.type === "context_expectancy" || r.type === "edge_decay"
                        ).length === 0 && (
                                <div className="text-xs text-muted">
                                    No market context models available.
                                </div>
                            )}

                        {trainResults
                            .filter(r =>
                                r.type === "context_expectancy" ||
                                r.type === "edge_decay"
                            )
                            .map(result => (
                                <div
                                    key={result.key}
                                    className="px-4 py-3 rounded-md text-sm"
                                    style={{
                                        backgroundColor: "var(--bg-tertiary)",
                                        border: "1px solid var(--border-color)"
                                    }}
                                >
                                    <div className="font-medium">
                                        {result.label}
                                    </div>

                                    <div
                                        className="text-xs mt-1"
                                        style={{ color: "var(--text-secondary)" }}
                                    >
                                        RMSE: {typeof result.rmse === "number"
                                            ? result.rmse.toFixed(3)
                                            : "—"}
                                    </div>
                                </div>
                            ))}
                    </div>
                )}



                {/* Tick Conversion */}
                <div
                    className="mt-8 p-5 space-y-3 max-w-xl"
                    style={panelStyle}
                >

                    <h2 className="text-sm font-semibold tracking-wide">
                        Tick to Candle Conversion (1m)
                    </h2>

                    <button
                        onClick={handleConvertTicks}
                        disabled={convertLoading}
                        className="h-10 px-6 rounded-md text-sm font-medium inline-flex items-center justify-center whitespace-nowrap"
                        style={{
                            backgroundColor: "var(--accent-up)",
                            color: "#ffffff"
                        }}
                    >
                        {convertLoading ? "Converting…" : "Convert Ticks"}
                    </button>

                    {convertMessage && (
                        <div
                            className="text-xs px-3 py-2 rounded-md"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                color: "var(--text-secondary)"
                            }}
                        >
                            {convertMessage}
                        </div>
                    )}
                </div>

                {/* ================= OFFLINE MARKET LABELING ================= */}
                <div
                    className="mt-8 p-5 space-y-4 max-w-xl"
                    style={panelStyle}
                >

                    <h2 className="text-sm font-semibold tracking-wide">
                        Offline Market Context Labeling
                    </h2>

                    <p
                        className="text-xs leading-relaxed"
                        style={{ color: "var(--text-secondary)" }}
                    >
                        Label historical candles with market structure and regime.
                        <br />
                        <span className="italic">
                            (Offline only — no future data leakage)
                        </span>
                    </p>

                    <input
                        type="number"
                        value={windowSize}
                        onChange={(e) => setWindowSize(+e.target.value)}
                        className="w-full h-10 px-3 rounded-md text-sm"
                        style={{
                            backgroundColor: "var(--bg-tertiary)",
                            border: "1px solid var(--border-color)",
                            color: "var(--text-primary)"
                        }}
                        placeholder="Context window size"
                    />

                    <button
                        onClick={handleOfflineLabeling}
                        disabled={labelLoading}
                        className="h-10 px-6 rounded-md inline-flex items-center justify-center gap-2 text-sm font-medium whitespace-nowrap"
                        style={{
                            backgroundColor: "var(--accent-up)",
                            color: "#ffffff"
                        }}
                    >
                        {labelLoading ? (
                            <Loader2 className="animate-spin w-4 h-4" />
                        ) : (
                            "Run Offline Labeling"
                        )}
                    </button>

                    {labelResult && (
                        <pre
                            className="text-xs px-3 py-2 rounded-md overflow-x-auto"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                color: "var(--text-secondary)"
                            }}
                        >
                            {JSON.stringify(labelResult, null, 2)}
                        </pre>
                    )}
                </div>


                {/* ================= OFFLINE SUCCESS OUTCOMES ================= */}
                <div
                    className="mt-8 p-5 space-y-4 max-w-xl"
                    style={panelStyle}
                >
                    <h2 className="text-sm font-semibold tracking-wide">
                        Offline Success Outcome Evaluation
                    </h2>

                    <p
                        className="text-xs leading-relaxed"
                        style={{ color: "var(--text-secondary)" }}
                    >
                        Evaluate how rule signals would have resolved
                        using phase-locked future candles.
                        <br />
                        <span className="italic">
                            (Offline only — lookahead is fixed by market phase)
                        </span>
                    </p>

                    <button
                        type="button"
                        onClick={handleOfflineSuccess}
                        disabled={outcomeLoading}
                        className="h-10 px-6 rounded-md inline-flex items-center justify-center gap-2 text-sm font-medium whitespace-nowrap"
                        style={{
                            backgroundColor: outcomeLoading
                                ? "var(--bg-tertiary)"
                                : "var(--accent-up)",
                            color: outcomeLoading
                                ? "var(--text-secondary)"
                                : "#ffffff"
                        }}
                    >
                        {outcomeLoading ? (
                            <>
                                <Loader2 className="animate-spin w-4 h-4" />
                                Computing…
                            </>
                        ) : (
                            "Compute Success Outcomes"
                        )}
                    </button>

                    {outcomeResult && (
                        <div
                            className="text-xs px-3 py-2 rounded-md"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                color: "var(--text-secondary)"
                            }}
                        >
                            {outcomeResult.error ? (
                                <div>{outcomeResult.error}</div>
                            ) : (
                                <pre className="whitespace-pre-wrap">
                                    {JSON.stringify(outcomeResult, null, 2)}
                                </pre>
                            )}
                        </div>
                    )}
                </div>


                {/* ================= RULE PERFORMANCE ================= */}
                <div
                    className="mt-8 p-5 space-y-4 max-w-xl"
                    style={panelStyle}
                >

                    <div className="flex justify-between items-center">
                        <h2 className="text-sm font-semibold tracking-wide">
                            Rule Performance (Market Context)
                        </h2>

                        <button
                            onClick={fetchRuleStats}
                            className="h-8 px-3 rounded-md text-xs font-medium inline-flex items-center"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                color: "var(--text-primary)"
                            }}
                        >
                            Refresh
                        </button>
                    </div>

                    {ruleStatsLoading && (
                        <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                            Loading rule statistics…
                        </div>
                    )}

                    {ruleStats?.as_of && (
                        <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                            Evaluated as of: {ruleStats.as_of}
                        </div>
                    )}

                    {ruleStats?.rules && ruleStats.rules.map(rule => (
                        <div
                            key={rule.name}
                            className="px-3 py-2 rounded-md flex justify-between items-center"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)"
                            }}
                        >
                            <div className="space-y-0.5">
                                <div className="text-sm font-medium">
                                    {rule.name}
                                </div>

                                <div
                                    className="text-xs"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Success: {(rule.success_rate * 100).toFixed(1)}% ·
                                    Failure: {(rule.failure_rate * 100).toFixed(1)}%
                                </div>

                                <div
                                    className="text-[11px]"
                                    style={{ color: "var(--text-secondary)" }}
                                >
                                    Evaluated at: {rule.evaluated_at}
                                </div>
                            </div>

                            <div
                                className="px-3 py-1 rounded-full text-[11px] font-medium whitespace-nowrap"
                                style={{
                                    backgroundColor:
                                        rule.status === "WORKING"
                                            ? "rgba(0,199,111,0.15)"
                                            : rule.status === "NOT_WORKING"
                                                ? "rgba(255,77,79,0.15)"
                                                : "rgba(255,193,7,0.15)",
                                    color:
                                        rule.status === "WORKING"
                                            ? "var(--accent-up)"
                                            : rule.status === "NOT_WORKING"
                                                ? "var(--accent-down)"
                                                : "var(--text-primary)"
                                }}
                            >
                                {rule.status}
                            </div>
                        </div>
                    ))}

                    {!ruleStatsLoading && !ruleStats && (
                        <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                            No rule diagnostics available yet.
                        </div>
                    )}
                </div>

                {/* ================= EQUITY CURVE ================= */}
                <div
                    className="mt-8 p-5 space-y-4 max-w-xl"
                    style={panelStyle}
                >

                    <h2 className="text-sm font-semibold tracking-wide">
                        Paper Trading Equity Curve
                    </h2>

                    {equityLoading && (
                        <div
                            className="text-xs"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            Loading equity curve…
                        </div>
                    )}

                    {!equityLoading && equityCurve.length === 0 && (
                        <div
                            className="text-xs"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            No equity data available.
                        </div>
                    )}

                    {!equityLoading && equityCurve.length > 0 && (
                        <div
                            className="max-h-64 overflow-y-auto rounded-md"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)"
                            }}
                        >
                            {equityCurve.map((p, idx) => (
                                <div
                                    key={idx}
                                    className="flex justify-between items-center px-3 py-1.5 text-xs"
                                    style={{
                                        borderBottom:
                                            idx !== equityCurve.length - 1
                                                ? "1px solid var(--border-color)"
                                                : "none"
                                    }}
                                >
                                    <span
                                        style={{ color: "var(--text-secondary)" }}
                                    >
                                        {new Date(p.time).toLocaleString()}
                                    </span>

                                    <span
                                        className="font-mono"
                                        style={{
                                            color:
                                                p.capital >= 10000
                                                    ? "var(--accent-up)"
                                                    : "var(--accent-down)"
                                        }}
                                    >
                                        ₹{p.capital.toFixed(2)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>


                {/* ================= PAPER TRADING SIMULATION ================= */}
                <div
                    className="mt-8 p-5 space-y-4 max-w-xl"
                    style={panelStyle}
                >
                    <h2 className="text-sm font-semibold tracking-wide">
                        Paper Trading Simulation
                    </h2>

                    {/* PARAMETERS */}
                    <div className="grid grid-cols-2 gap-4 text-xs">
                        {[
                            { label: "Risk Model", value: "Phase Adaptive" },
                            { label: "RR Model", value: "Phase Adaptive" },
                            { label: "Max Trades / Day", value: "5" },
                            { label: "Capital Stop", value: "₹7,000" },
                        ].map((item) => (
                            <div
                                key={item.label}
                                className="p-3 rounded-md"
                                style={{
                                    backgroundColor: "var(--bg-tertiary)",
                                    border: "1px solid var(--border-color)",
                                }}
                            >
                                <div style={{ color: "var(--text-secondary)" }}>
                                    {item.label}
                                </div>
                                <div className="font-medium">
                                    {item.value}
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* THRESHOLD */}
                    <div className="space-y-1">
                        <label
                            className="block text-xs"
                            style={{ color: "var(--text-secondary)" }}
                        >
                            ML Threshold
                        </label>
                        <select
                            value={threshold}
                            onChange={(e) => setThreshold(Number(e.target.value))}
                            className="w-full h-10 px-3 rounded-md text-sm"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                color: "var(--text-primary)",
                            }}
                        >
                            <option value={0.5}>0.5</option>
                            <option value={0.6}>0.6</option>
                            <option value={0.7}>0.7</option>
                        </select>
                    </div>

                    {/* RUN PAPER TRADING */}
                    <button
                        onClick={runPaperTrading}
                        disabled={paperLoading || !trainResults?.model_run_id}
                        className="h-10 px-6 rounded-md inline-flex items-center justify-center gap-2 text-sm font-medium whitespace-nowrap"
                        style={{
                            backgroundColor:
                                paperLoading || !trainResults?.model_run_id
                                    ? "var(--border-color)"
                                    : "var(--accent-up)",
                            color: "#ffffff",
                        }}
                    >
                        {paperLoading ? (
                            <Loader2 className="animate-spin w-4 h-4" />
                        ) : !trainResults?.model_run_id ? (
                            "Train Model First"
                        ) : (
                            "Run Paper Trading"
                        )}
                    </button>

                    {/* SUMMARY */}
                    {paperResult && (
                        <div
                            className="p-4 rounded-md text-xs"
                            style={{
                                backgroundColor: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                            }}
                        >
                            {paperResult.error ? (
                                <div style={{ color: "var(--accent-down)" }}>
                                    {paperResult.error}
                                </div>
                            ) : (
                                <>
                                    <h3 className="text-sm font-semibold mb-2">
                                        Simulation Summary
                                    </h3>
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>Start Capital: ₹10,000</div>
                                        <div>Final Capital: ₹{paperResult.final_capital}</div>
                                        <div>Total Trades: {paperResult.total_trades}</div>
                                        <div>
                                            Win Rate: {(paperResult.win_rate * 100).toFixed(1)}%
                                        </div>
                                        <div>
                                            Max Drawdown: {paperResult.max_drawdown_pct}%
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}



