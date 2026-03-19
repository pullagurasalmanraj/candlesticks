import React, { useState, useEffect, useRef } from "react";
import { LAYOUT, useTheme } from "../context/ThemeContext";

import SearchTrainCard from "./lstm/SearchTrainCard";
import TrainingResults from "./lstm/TrainingResults";
import ConversionCard from "./lstm/ConversionCard";
import OfflineLabelingCard from "./lstm/OfflineLabelingCard";
import OfflineOutcomesCard from "./lstm/OfflineOutcomesCard";
import RulePerformanceCard from "./lstm/RulePerformanceCard";
import EquityCurveCard from "./lstm/EquityCurveCard";
import PaperTradingCard from "./lstm/PaperTradingCard";
import OptionsContractSearchCard from "./lstm/OptionsContractSearchCard";







export default function MLTrainingPage() {
    const { theme } = useTheme();

    const [symbol, setSymbol] = useState("");
    const [filtered, setFiltered] = useState([]);
    const [timeframe, setTimeframe] = useState("1m");
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
    const [modelRunId, setModelRunId] = useState(null);

    const [search, setSearch] = useState("");

    const [searching, setSearching] = useState(false);

    // Options contract search
    const [contractQuery, setContractQuery] = useState("");
    const [contractSearching, setContractSearching] = useState(false);
    const [contractResults, setContractResults] = useState([]);
    const [selectedContract, setSelectedContract] = useState(null);

    const searchAbortRef = useRef(null);
    const contractAbortRef = useRef(null);
    const latestSearchRef = useRef("");
    const latestContractQueryRef = useRef("");
    const justSelectedRef = useRef(false);  // prevents search re-firing after selection

    // (panelStyle no longer needed; extracted into card components)



    useEffect(() => {
        const query = (search || "").trim();
        latestSearchRef.current = query;

        if (query.length < 2) {
            setSearchResults([]);
            setSearching(false);
            return;
        }

        // Skip search if this change came from selecting an instrument
        if (justSelectedRef.current) {
            justSelectedRef.current = false;
            return;
        }

        if (searchAbortRef.current) {
            searchAbortRef.current.abort();
        }

        const controller = new AbortController();
        searchAbortRef.current = controller;

        const t = setTimeout(async () => {
            try {
                setSearching(true);
                const res = await fetch(`/api/instruments?q=${encodeURIComponent(query)}`, {
                    signal: controller.signal,
                });
                const data = await res.json();

                if (latestSearchRef.current !== query) return; // stale response

                const uniqueInstruments = Array.isArray(data.instruments)
                    ? Array.from(
                          new Map(
                              data.instruments
                                  .filter((item) => item && item.instrument_key)
                                  .map((item) => [item.instrument_key, item])
                          ).values()
                      )
                    : [];

                setSearchResults(uniqueInstruments);
            } catch (e) {
                if (e.name !== "AbortError") {
                    console.error(e);
                    setSearchResults([]);
                }
            } finally {
                if (latestSearchRef.current === query) {
                    setSearching(false);
                }
            }
        }, 220);

        return () => {
            clearTimeout(t);
            controller.abort();
        };
    }, [search]);

    useEffect(() => {
        const q = (contractQuery || "").trim().toUpperCase();
        latestContractQueryRef.current = q;

        if (q.length < 2) {
            setContractResults([]);
            setContractSearching(false);
            return;
        }

        if (contractAbortRef.current) {
            contractAbortRef.current.abort();
        }

        const controller = new AbortController();
        contractAbortRef.current = controller;

        const t = setTimeout(async () => {
            try {
                setContractSearching(true);
                const res = await fetch(`/api/options/contracts?q=${encodeURIComponent(q)}`, {
                    signal: controller.signal,
                });
                const data = await res.json();

                if (latestContractQueryRef.current !== q) return;

                const uniqueContracts = Array.isArray(data.contracts)
                    ? Array.from(
                          new Map(
                              data.contracts
                                  .filter((c) => c && c.instrument_key)
                                  .map((c) => [c.instrument_key, c])
                          ).values()
                      )
                    : [];

                setContractResults(uniqueContracts);
            } catch (e) {
                if (e.name !== "AbortError") {
                    console.error(e);
                    setContractResults([]);
                }
            } finally {
                if (latestContractQueryRef.current === q) {
                    setContractSearching(false);
                }
            }
        }, 220);

        return () => {
            clearTimeout(t);
            controller.abort();
        };
    }, [contractQuery]);




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
        setModelRunId(null);

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

            setModelRunId(data.model_run_id || null);

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
            // 10 minute timeout — 89k rows takes 3-4 minutes to process
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 600000);

            const res = await fetch("/api/offline/label-market-context", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, windowSize }),
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            if (!res.ok) {
                const text = await res.text();
                throw new Error(text.startsWith("<") ? "Server error (check Flask logs)" : text);
            }
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
            // 10 minute timeout for heavy computation
            const controller2 = new AbortController();
            const timeoutId2 = setTimeout(() => controller2.abort(), 600000);

            const res = await fetch("/api/offline/calc-strategy-outcomes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                signal: controller2.signal,
                body: JSON.stringify({
                    symbol,
                    timeframe
                    // ✅ NO lookahead
                    // optional later: from_date, to_date
                })
            });

            clearTimeout(timeoutId2);

            if (!res.ok) {
                const text = await res.text();
                throw new Error(text.startsWith("<") ? "Server error (check Flask logs)" : text);
            }

            let data;
            try {
                data = await res.json();
            } catch {
                throw new Error("Server did not return JSON — request may have timed out");
            }

            setOutcomeResult(data);

        } catch (e) {
            console.error(e);
            setOutcomeResult({
                error: e.name === "AbortError" ? "Request timed out after 10 minutes" : "Request failed",
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
        if (!modelRunId) return alert("Train model first");

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
                    model_run_id: modelRunId,
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
        if (!symbol || !modelRunId) {
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
                    model_run_id: modelRunId,
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


    // Pipeline step tracker
    const steps = [
        { id: 1, label: "Search & Train",   done: !!modelRunId },
        { id: 2, label: "Data Pipeline",    done: !!convertMessage },
        { id: 3, label: "Label Context",    done: !!(labelResult && !labelResult.error) },
        { id: 4, label: "Outcomes",         done: !!(outcomeResult && outcomeResult.status === "SUCCESS") },
        { id: 5, label: "Paper Trade",      done: !!(paperResult && !paperResult.error) },
    ];

    return (
        <div style={{
            minHeight: "calc(100vh - var(--navbar-height))",
            background: "var(--bg-primary)",
            color: "var(--text-primary)",
            fontFamily: "var(--font-body)",
        }}>
            <style>{`
                .ml-page {
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 20px var(--content-padding, 20px);
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                }
                /* Pipeline bar */
                .ml-pipeline {
                    display: flex;
                    align-items: stretch;
                    background: var(--bg-secondary);
                    border: 1px solid var(--border-color);
                    border-radius: 10px;
                    overflow: hidden;
                }
                .ml-step {
                    flex: 1;
                    display: flex;
                    align-items: center;
                    gap: 7px;
                    padding: 10px 14px;
                    font-size: 0.72rem;
                    font-weight: 600;
                    color: var(--text-muted);
                    border-right: 1px solid var(--border-subtle);
                    white-space: nowrap;
                    transition: all 0.15s ease;
                }
                .ml-step:last-child { border-right: none; }
                .ml-step.done   { color: var(--accent-up); }
                .ml-step.active { color: var(--text-primary); }
                .ml-step-num {
                    width: 20px; height: 20px;
                    border-radius: 50%;
                    border: 1.5px solid currentColor;
                    display: flex; align-items: center; justify-content: center;
                    font-size: 0.6rem; font-weight: 700; flex-shrink: 0;
                }
                .ml-step.done .ml-step-num {
                    background: var(--accent-up);
                    border-color: var(--accent-up);
                    color: #fff;
                }
                /* Two-column layout */
                .ml-layout {
                    display: grid;
                    grid-template-columns: 300px 1fr;
                    gap: 16px;
                    align-items: start;
                }
                /* Left rail */
                .ml-rail {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                    min-width: 0;
                }
                /* Right area */
                .ml-right {
                    display: flex;
                    flex-direction: column;
                    gap: 14px;
                    min-width: 0;
                }
                .ml-row-2 {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 14px;
                }
                @media (max-width: 1100px) {
                    .ml-layout { grid-template-columns: 1fr; }
                    .ml-row-2  { grid-template-columns: 1fr; }
                }
                @media (max-width: 700px) {
                    .ml-pipeline { flex-wrap: wrap; }
                    .ml-step     { flex: none; width: 50%; border-bottom: 1px solid var(--border-subtle); }
                }
            `}</style>

            <div className="ml-page">

                {/* ── Pipeline progress ── */}
                <div className="ml-pipeline">
                    {steps.map(s => (
                        <div key={s.id} className={`ml-step ${s.done ? "done" : "active"}`}>
                            <span className="ml-step-num">{s.done ? "✓" : s.id}</span>
                            {s.label}
                        </div>
                    ))}
                </div>

                {/* ── Main layout ── */}
                <div className="ml-layout">

                    {/* LEFT RAIL — action cards, workflow order */}
                    <div className="ml-rail">

                        {/* Step 1: Search + Train */}
                        <SearchTrainCard
                            theme={theme}
                            symbol={symbol}
                            modelRunId={modelRunId}
                            search={search}
                            searching={searching}
                            onSearchChange={handleSearch}
                            searchResults={searchResults}
                            onSelectInstrument={(inst) => {
                                justSelectedRef.current = true;
                                setSymbol(inst.symbol);
                                setSearch(inst.symbol);
                                setSearchResults([]);
                                if (searchAbortRef.current) searchAbortRef.current.abort();
                            }}
                            timeframe={timeframe}
                            onTimeframeChange={setTimeframe}
                            loading={loading}
                            onTrain={handleTrain}
                            compareLoading={compareLoading}
                            onCompareThresholds={compareThresholds}
                        />

                        {/* Step 2: Data Pipeline (live tick → candle) */}
                        <ConversionCard
                            symbol={symbol}
                            convertLoading={convertLoading}
                            convertMessage={convertMessage}
                            onConvertTicks={handleConvertTicks}
                        />

                        {/* Step 3: Label market context */}
                        <OfflineLabelingCard
                            symbol={symbol}
                            windowSize={windowSize}
                            onWindowSizeChange={setWindowSize}
                            labelLoading={labelLoading}
                            onRunLabeling={handleOfflineLabeling}
                            labelResult={labelResult}
                        />

                        {/* Step 4: Compute outcomes */}
                        <OfflineOutcomesCard
                            symbol={symbol}
                            outcomeLoading={outcomeLoading}
                            onComputeOutcomes={handleOfflineSuccess}
                            outcomeResult={outcomeResult}
                        />

                    </div>

                    {/* RIGHT — results and analysis */}
                    <div className="ml-right">

                        {/* Training results */}
                        <TrainingResults trainResults={trainResults} />

                        {/* Rule performance + options search */}
                        <div className="ml-row-2">
                            <RulePerformanceCard
                                symbol={symbol}
                                ruleStatsLoading={ruleStatsLoading}
                                ruleStats={ruleStats}
                                onRefresh={fetchRuleStats}
                            />
                            <OptionsContractSearchCard
                                query={contractQuery}
                                onQueryChange={setContractQuery}
                                loading={contractSearching}
                                results={contractResults}
                                selected={selectedContract}
                                onSelect={setSelectedContract}
                            />
                        </div>

                        {/* Equity curve */}
                        <EquityCurveCard
                            equityLoading={equityLoading}
                            equityCurve={equityCurve}
                        />

                        {/* Paper trading */}
                        <PaperTradingCard
                            riskPct={riskPct}
                            rrRatio={rrRatio}
                            threshold={threshold}
                            onThresholdChange={setThreshold}
                            paperLoading={paperLoading}
                            modelRunId={modelRunId}
                            onRunPaperTrading={runPaperTrading}
                            paperProgress={paperProgress}
                            paperPercent={paperPercent}
                            paperResult={paperResult}
                        />

                    </div>
                </div>
            </div>
        </div>
    );
}



