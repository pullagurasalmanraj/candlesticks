// LstmPredictor.jsx — Quant ML Strategy Engine
// Refined 5-Step Quantitative Strategy & ML Pipeline:
//   Step 1: Market Phase Context Labeling (15m → 5m → 3m → 1m)
//   Step 2: MFE / MAE Phase Parameter Calibration (TP/SL/Lookahead)
//   Step 3: Strategy Outcome Calculation
//   Step 4: Machine Learning Model Training (LightGBM)
//   Step 5: Paper Trading Simulation, Backtest & Live Execution Signals
// ──────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useRef } from "react";
import { useTheme } from "../context/ThemeContext";

// ─── Micro Atoms ─────────────────────────────────────────────────────────────
const Spinner = ({ sz = 13 }) => (
    <svg width={sz} height={sz} viewBox="0 0 24 24" fill="none"
        style={{ animation: "ml-spin .75s linear infinite", flexShrink: 0 }}>
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="42 14" />
    </svg>
);

const Badge = ({ children, tone = "neutral" }) => {
    const map = {
        neutral: ["var(--bg-tertiary)", "var(--text-muted)", "var(--border-subtle)"],
        up: ["rgba(34,197,94,.12)", "var(--accent-up)", "rgba(34,197,94,.28)"],
        down: ["rgba(239,68,68,.12)", "var(--accent-down)", "rgba(239,68,68,.28)"],
        blue: ["rgba(59,130,246,.12)", "var(--accent-blue,#3b82f6)", "rgba(59,130,246,.28)"],
        amber: ["rgba(245,158,11,.12)", "#f59e0b", "rgba(245,158,11,.28)"],
    };
    const [bg, color, border] = map[tone] || map.neutral;
    return (
        <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 4, fontSize: "0.68rem", fontWeight: 700, letterSpacing: ".05em", background: bg, color, border: `1px solid ${border}`, whiteSpace: "nowrap" }}>
            {children}
        </span>
    );
};

const Btn = ({ children, onClick, loading, disabled, variant = "primary", size = "md" }) => {
    const pad = size === "sm" ? "5px 12px" : size === "lg" ? "10px 22px" : "7px 16px";
    const fz = size === "sm" ? "0.72rem" : size === "lg" ? "0.9rem" : "0.8rem";
    const styles = {
        primary: { bg: "var(--accent-blue,#3b82f6)", color: "#fff", border: "transparent" },
        secondary: { bg: "var(--bg-tertiary)", color: "var(--text-primary)", border: "var(--border-color)" },
        ghost: { bg: "transparent", color: "var(--text-muted)", border: "var(--border-subtle)" },
        success: { bg: "var(--accent-up)", color: "#fff", border: "transparent" },
        danger: { bg: "rgba(239,68,68,.1)", color: "var(--accent-down)", border: "rgba(239,68,68,.3)" },
    };
    const v = styles[variant] || styles.primary;
    const off = disabled || loading;
    return (
        <button disabled={off} onClick={onClick}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: pad, borderRadius: "var(--button-radius)", border: `1px solid ${v.border}`, background: v.bg, color: v.color, fontSize: fz, fontWeight: 600, cursor: off ? "not-allowed" : "pointer", opacity: off ? .45 : 1, transition: "opacity .15s, transform .1s", whiteSpace: "nowrap" }}>
            {loading && <Spinner sz={12} />}{children}
        </button>
    );
};

const Lbl = ({ children }) => (
    <span style={{ fontSize: "0.7rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>{children}</span>
);

const Inp = ({ value, onChange, placeholder, type = "text", step }) => (
    <input value={value} type={type} step={step} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        style={{ width: "100%", boxSizing: "border-box", padding: "8px 12px", borderRadius: "var(--input-radius)", background: "var(--bg-input,var(--bg-tertiary))", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: "0.85rem", outline: "none" }} />
);

const Sel = ({ value, onChange, options }) => (
    <select value={value} onChange={e => onChange(e.target.value)}
        style={{ width: "100%", boxSizing: "border-box", padding: "8px 12px", borderRadius: "var(--input-radius)", background: "var(--bg-input,var(--bg-tertiary))", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: "0.85rem", outline: "none" }}>
        {options.map(o => <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>)}
    </select>
);

const Fld = ({ label, hint, children }) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {label && <Lbl>{label}</Lbl>}
        {children}
        {hint && <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{hint}</span>}
    </div>
);

const StepPanel = ({ stepNum, title, description, badge, active, completed, children }) => (
    <div style={{
        background: "var(--bg-secondary)",
        border: `1px solid ${active ? "var(--accent-blue)" : "var(--border-color)"}`,
        borderRadius: "var(--card-radius)",
        overflow: "hidden",
        boxShadow: active ? "0 0 0 1px rgba(59,130,246,0.2), var(--shadow-card)" : "var(--shadow-card)",
        transition: "all 0.2s ease"
    }}>
        <div style={{
            padding: "12px 18px",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: active ? "rgba(59,130,246,0.06)" : "transparent"
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                    width: 26, height: 26, borderRadius: "50%",
                    background: completed ? "var(--accent-up)" : active ? "var(--accent-blue)" : "var(--bg-tertiary)",
                    color: completed || active ? "#fff" : "var(--text-muted)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontWeight: 700, fontSize: "0.75rem", flexShrink: 0
                }}>
                    {completed ? "✓" : stepNum}
                </div>
                <div>
                    <div style={{ fontSize: "0.9rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "var(--text-primary)" }}>{title}</div>
                    {description && <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 1 }}>{description}</div>}
                </div>
            </div>
            {badge}
        </div>
        <div style={{ padding: 18 }}>{children}</div>
    </div>
);

const Alert = ({ type = "info", children }) => {
    const c = { info: "var(--accent-blue,#3b82f6)", error: "var(--accent-down)", success: "var(--accent-up)", warn: "#f59e0b" }[type] || "#3b82f6";
    return <div style={{ padding: "10px 14px", borderRadius: "var(--input-radius)", background: `${c}11`, border: `1px solid ${c}30`, fontSize: "0.78rem", color: c, lineHeight: 1.55 }}>{children}</div>;
};

const Stat = ({ label, value, tone, sub }) => {
    const color = tone === "up" ? "var(--accent-up)" : tone === "down" ? "var(--accent-down)" : "var(--text-primary)";
    return (
        <div style={{ background: "var(--bg-tertiary)", borderRadius: 8, padding: "10px 12px", textAlign: "center", border: "1px solid var(--border-subtle)" }}>
            <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: ".05em" }}>{label}</div>
            <div style={{ fontSize: "1rem", fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>{value ?? "—"}</div>
            {sub && <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>}
        </div>
    );
};

const TfPill = ({ tf, active, onClick, suffix }) => (
    <button onClick={() => onClick(tf)}
        style={{ padding: "5px 12px", borderRadius: 6, border: `1px solid ${active ? "var(--accent-blue,#3b82f6)" : "var(--border-color)"}`, background: active ? "var(--accent-blue,#3b82f6)" : "var(--bg-tertiary)", color: active ? "#fff" : "var(--text-muted)", fontSize: "0.75rem", fontWeight: 700, cursor: "pointer", transition: "all .12s" }}>
        {tf}{suffix || ""}
    </button>
);

// Persistent state hook that automatically syncs state with localStorage until logout
function usePersistedState(key, defaultValue) {
    const [state, setState] = useState(() => {
        try {
            const saved = localStorage.getItem(`quant_ml_${key}`);
            if (saved !== null && saved !== "undefined") {
                return JSON.parse(saved);
            }
        } catch (e) {
            console.error("Error reading localStorage for key:", key, e);
        }
        return defaultValue;
    });

    useEffect(() => {
        try {
            if (state === undefined) {
                localStorage.removeItem(`quant_ml_${key}`);
            } else {
                localStorage.setItem(`quant_ml_${key}`, JSON.stringify(state));
            }
        } catch (e) {
            console.error("Error writing localStorage for key:", key, e);
        }
    }, [key, state]);

    return [state, setState];
}

// ─── Constants ───────────────────────────────────────────────────────────────
const TF_PRI = ["1m", "3m", "5m", "15m"];
const TF_ALL = ["15m", "5m", "3m", "1m"];

export default function QuantMLStrategyEngine() {
    const { theme } = useTheme();

    // Navigation Step (1 to 5) — Persisted across page refresh
    const [currentStep, setCurrentStep] = usePersistedState("currentStep", 1);
    const [viewMode, setViewMode] = usePersistedState("viewMode", "sequence");

    // Setup: Symbol & Timeframe — Persisted across page refresh
    const [symbol, setSymbol] = usePersistedState("symbol", "");
    const [search, setSearch] = useState("");
    const [searching, setSearching] = useState(false);
    const [searchResults, setSearchResults] = useState([]);
    const [timeframe, setTimeframe] = usePersistedState("timeframe", "15m");
    const [htf, setHtf] = usePersistedState("htf", "15m");
    const [mtf, setMtf] = usePersistedState("mtf", "5m");

    // Step 1 — Market Phase Context Labeling — Persisted across page refresh
    const [labelTf, setLabelTf] = usePersistedState("labelTf", "15m");
    const [labelLoading, setLabelLoading] = useState(false);
    const [labelResults, setLabelResults] = usePersistedState("labelResults", {});

    // Step 2 — Raw Baseline Strategy Outcomes — Persisted across page refresh
    const [rawOutcomeLoading, setRawOutcomeLoading] = useState(false);
    const [rawOutcomeResult, setRawOutcomeResult] = usePersistedState("rawOutcomeResult", null);

    // Step 3 — MFE / MAE Calibration — Persisted across page refresh
    const [calibTf, setCalibTf] = usePersistedState("calibTf", "15m");
    const [calibLoading, setCalibrateLoading] = useState(false);
    const [calibResult, setCalibrateResult] = usePersistedState("calibResult", null);
    const [tpPct, setTpPct] = usePersistedState("tpPct", 60);
    const [slPct, setSlPct] = usePersistedState("slPct", 25);
    const [laPct, setLaPct] = usePersistedState("laPct", 75);
    const [minSamples, setMinSamples] = usePersistedState("minSamples", 30);

    // Step 4 — Calibrated Strategy Outcomes — Persisted across page refresh
    const [outcomeLoading, setOutcomeLoading] = useState(false);
    const [outcomeResult, setOutcomeResult] = usePersistedState("outcomeResult", null);

    // Step 4 — ML Model Training — Persisted across page refresh
    const [trainLoading, setTrainLoading] = useState(false);
    const [trainResults, setTrainResults] = usePersistedState("trainResults", null);
    const [modelRunId, setModelRunId] = usePersistedState("modelRunId", null);
    const [cmpLoading, setCmpLoading] = useState(false);
    const [cmpResult, setCmpResult] = usePersistedState("cmpResult", null);

    // Step 5 — Paper Trading & Live Signals — Persisted across page refresh
    const [runIdLtf, setRunIdLtf] = usePersistedState("runIdLtf", "");
    const [runIdMtf, setRunIdMtf] = usePersistedState("runIdMtf", "");
    const [runIdHtf, setRunIdHtf] = usePersistedState("runIdHtf", "");
    const [sigLoading, setSigLoading] = useState(false);
    const [sigResult, setSigResult] = usePersistedState("sigResult", null);
    const [htfSigLoading, setHtfSigLoading] = useState(false);
    const [htfSigResult, setHtfSigResult] = usePersistedState("htfSigResult", null);
    const [paperLoading, setPaperLoading] = useState(false);
    const [paperResult, setPaperResult] = usePersistedState("paperResult", null);
    const [paperPercent, setPaperPercent] = useState(0);
    const [paperProgress, setPaperProgress] = useState("");
    const [threshold, setThreshold] = usePersistedState("threshold", 0.60);
    const [startCap, setStartCap] = usePersistedState("startCap", 100000);
    const [marginPS, setMarginPS] = usePersistedState("marginPS", 21.68);
    const [equityCurve, setEquityCurve] = usePersistedState("equityCurve", []);
    const [equityLoading, setEquityLoading] = useState(false);

    // Refs
    const searchAbortRef = useRef(null);
    const latestSearchRef = useRef("");
    const justSelectedRef = useRef(false);
    const paperTimerRef = useRef(null);

    // Instrument search effect
    useEffect(() => {
        const q = (search || "").trim();
        latestSearchRef.current = q;
        if (q.length < 2) { setSearchResults([]); setSearching(false); return; }
        if (justSelectedRef.current) { justSelectedRef.current = false; return; }
        if (searchAbortRef.current) searchAbortRef.current.abort();
        const ctrl = new AbortController();
        searchAbortRef.current = ctrl;
        const tid = setTimeout(async () => {
            try {
                setSearching(true);
                const res = await fetch(`/api/instruments?q=${encodeURIComponent(q)}`, { signal: ctrl.signal });
                const data = await res.json();
                if (latestSearchRef.current !== q) return;
                const uniq = Array.isArray(data.instruments)
                    ? Array.from(new Map(data.instruments.filter(i => i?.instrument_key).map(i => [i.instrument_key, i])).values())
                    : [];
                setSearchResults(uniq);
            } catch (e) { if (e.name !== "AbortError") setSearchResults([]); }
            finally { if (latestSearchRef.current === q) setSearching(false); }
        }, 220);
        return () => { clearTimeout(tid); ctrl.abort(); };
    }, [search]);

    // Handlers
    const handleResetAllState = () => {
        if (!window.confirm("Are you sure you want to clear all saved session state and reset to default?")) return;
        Object.keys(localStorage).forEach(key => {
            if (key.startsWith("quant_ml_")) {
                localStorage.removeItem(key);
            }
        });
        window.location.reload();
    };

    const handleSearch = v => { const u = v.toUpperCase(); setSymbol(u); setSearch(u); };

    const selectInstrument = inst => {
        justSelectedRef.current = true;
        setSymbol(inst.symbol); setSearch(inst.symbol); setSearchResults([]);
        if (searchAbortRef.current) searchAbortRef.current.abort();
    };

    // Global Timeframe Hierarchy Synchronizer for Entire Pipeline
    const TF_HIERARCHY = {
        "15m": { ltf: "15m", mtf: "15m", htf: "15m" },
        "5m":  { ltf: "5m",  mtf: "15m", htf: "15m" },
        "3m":  { ltf: "3m",  mtf: "5m",  htf: "15m" },
        "1m":  { ltf: "1m",  mtf: "5m",  htf: "15m" },
    };

    const handleGlobalTimeframeChange = (newTf) => {
        setTimeframe(newTf);
        setLabelTf(newTf);
        setCalibTf(newTf);
        const map = TF_HIERARCHY[newTf] || { ltf: newTf, mtf: "5m", htf: "15m" };
        setMtf(map.mtf);
        setHtf(map.htf);
    };

    // Step 1: Label Market Context
    const handleLabel = async () => {
        if (!symbol) return alert("Select a symbol first");
        const tf = timeframe;
        setLabelLoading(true);
        setLabelResults(p => ({ ...p, [tf]: { _running: true } }));
        try {
            const ctrl = new AbortController();
            setTimeout(() => ctrl.abort(), 600_000);
            const res = await fetch("/api/offline/label-market-context", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe: tf }),
                signal: ctrl.signal,
            });
            if (!res.ok) throw new Error(await res.text());
            const labelData = await res.json();
            setLabelResults(p => ({ ...p, [tf]: labelData }));
        } catch (e) {
            setLabelResults(p => ({ ...p, [tf]: { error: e.name === "AbortError" ? "Timed out (10 min)" : e.message } }));
        }
        setLabelLoading(false);
    };

    // Step 2: Calculate Raw Baseline Strategy Outcomes (Initial Run with Defaults)
    const handleRawOutcomes = async () => {
        if (!symbol) return alert("Select a symbol first");
        setRawOutcomeLoading(true);
        setRawOutcomeResult({ _running: true, message: "Computing raw baseline strategy outcomes with default phase parameters…" });
        try {
            const ctrl = new AbortController();
            setTimeout(() => ctrl.abort(), 600_000);
            const res = await fetch("/api/offline/calc-strategy-outcomes", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe }),
                signal: ctrl.signal,
            });
            if (!res.ok) throw new Error(await res.text());
            setRawOutcomeResult(await res.json());
        } catch (e) {
            setRawOutcomeResult({ error: e.name === "AbortError" ? "Timed out (10 min)" : e.message });
        }
        setRawOutcomeLoading(false);
    };

    // Step 3: Calibrate Params from Raw Outcomes
    const handleCalibrate = async () => {
        if (!symbol) return alert("Select a symbol first");
        setCalibrateLoading(true); setCalibrateResult(null);
        try {
            const res = await fetch("/api/offline/calibrate-phase-params", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, tp_percentile: tpPct, sl_percentile: slPct, la_percentile: laPct, min_samples: minSamples }),
            });
            setCalibrateResult(await res.json());
        } catch (e) { setCalibrateResult({ error: e.message }); }
        setCalibrateLoading(false);
    };

    // Step 4: Calculate Calibrated Strategy Outcomes (Final Run with Optimal TP/SL)
    const handleOutcomes = async () => {
        if (!symbol) return alert("Select a symbol first");
        setOutcomeLoading(true);
        setOutcomeResult({ _running: true, message: "Re-evaluating strategy outcomes using optimal calibrated parameters…" });
        try {
            const ctrl = new AbortController();
            setTimeout(() => ctrl.abort(), 600_000);
            const res = await fetch("/api/offline/calc-strategy-outcomes", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe }),
                signal: ctrl.signal,
            });
            if (!res.ok) throw new Error(await res.text());
            setOutcomeResult(await res.json());
        } catch (e) {
            setOutcomeResult({ error: e.name === "AbortError" ? "Timed out (10 min)" : e.message });
        }
        setOutcomeLoading(false);
    };

    // Step 4: Train Model
    const handleTrain = async () => {
        if (!symbol) return alert("Select a symbol first");
        setTrainLoading(true); setTrainResults(null); setModelRunId(null);
        try {
            const res = await fetch("/api/train-pipeline", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, htf, mtf }),
            });
            const data = await res.json();
            if (data.status !== "SUCCESS") throw new Error(data.error || "Training failed");
            setModelRunId(data.model_run_id);
            setRunIdLtf(String(data.model_run_id || ""));
            setTrainResults(data);
        } catch (e) { setTrainResults({ error: e.message }); }
        setTrainLoading(false);
    };

    const compareThresholds = async () => {
        if (!symbol || !modelRunId) return alert("Train a model first");
        setCmpLoading(true); setCmpResult(null);
        try {
            const res = await fetch("/api/paper-trade/compare-thresholds", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, model_run_id: modelRunId, starting_capital: startCap, thresholds: [0.55, 0.60, 0.65, 0.70] }),
            });
            setCmpResult(await res.json());
        } catch (e) { setCmpResult({ error: e.message }); }
        setCmpLoading(false);
    };

    // Step 5: Live Signal & Paper Trade
    const handlePredictSignal = async () => {
        if (!symbol || !runIdLtf) return alert("Need symbol + LTF model run ID");
        setSigLoading(true); setSigResult(null); setHtfSigResult(null);
        try {
            const res = await fetch("/api/live/predict-signal", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, model_run_id: parseInt(runIdLtf), threshold }),
            });
            setSigResult(await res.json());
        } catch (e) { setSigResult({ error: e.message }); }
        setSigLoading(false);
    };

    const handleHtfSignal = async () => {
        if (!symbol || !runIdLtf) return alert("Need symbol + LTF model run ID");
        setHtfSigLoading(true); setHtfSigResult(null); setSigResult(null);
        try {
            const res = await fetch("/api/live/predict-signal-htf", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol, timeframe, threshold,
                    model_run_id_ltf: runIdLtf ? parseInt(runIdLtf) : undefined,
                    model_run_id_mtf: runIdMtf ? parseInt(runIdMtf) : undefined,
                    model_run_id_htf: runIdHtf ? parseInt(runIdHtf) : undefined,
                }),
            });
            setHtfSigResult(await res.json());
        } catch (e) { setHtfSigResult({ error: e.message }); }
        setHtfSigLoading(false);
    };

    const fakeProg = () => {
        let p = 5; setPaperPercent(5);
        paperTimerRef.current = setInterval(() => {
            p += Math.random() * 7;
            if (p >= 90) { p = 90; clearInterval(paperTimerRef.current); }
            setPaperPercent(Math.floor(p));
        }, 700);
    };

    const runPaperTrading = async () => {
        if (!symbol) return alert("Select a symbol first");
        if (!modelRunId) return alert("Train a model first (Step 5)");
        setPaperLoading(true); setPaperResult(null); setEquityCurve([]);
        setPaperProgress("Initialising paper trading engine…"); fakeProg();
        try {
            setPaperProgress("Running leverage-based trade simulation…");
            const res = await fetch("/api/paper-trade/run", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, model_run_id: modelRunId, margin_per_share: marginPS, starting_capital: startCap, threshold }),
            });
            const data = await res.json();
            if (!res.ok) { setPaperResult({ error: data.error }); return; }
            setPaperResult(data); setPaperPercent(98);
            setPaperProgress("Fetching equity curve…");
            if (data.paper_trade_run_id) {
                setEquityLoading(true);
                try {
                    const eq = await fetch(`/api/paper-trade/equity-curve?run_id=${data.paper_trade_run_id}`);
                    setEquityCurve((await eq.json()).curve || []);
                } catch { /* non-fatal */ }
                setEquityLoading(false);
            }
            setPaperPercent(100); setPaperProgress("Completed");
        } catch (e) { setPaperResult({ error: e.message }); setPaperPercent(0); }
        finally { clearInterval(paperTimerRef.current); setPaperLoading(false); }
    };

    // Derived Completion States
    const step1Done = Object.values(labelResults).some(r => r?.market_rows > 0 || r?.status === "SUCCESS");
    const step2Done = rawOutcomeResult?.status === "SUCCESS";
    const step3Done = calibResult?.phases_calibrated > 0;
    const step4Done = outcomeResult?.status === "SUCCESS";
    const step5Done = !!modelRunId;
    const step6Done = paperResult && !paperResult.error;

    const pipelineSteps = [
        { id: 1, title: "Market Context Labeling", desc: "Phase Labeling (15m→1m)", done: step1Done },
        { id: 2, title: "Raw Strategy Outcomes", desc: "Baseline Trade Outcomes", done: step2Done },
        { id: 3, title: "MFE/MAE Calibration", desc: "Optimal TP/SL Params", done: step3Done },
        { id: 4, title: "Calibrated Outcomes", desc: "Recalculate with Optimal TP/SL", done: step4Done },
        { id: 5, title: "ML Model Training", desc: "LightGBM Classifier", done: step5Done },
        { id: 6, title: "Paper Trade & Signals", desc: "Simulation & Execution", done: step6Done },
    ];

    const activeSig = htfSigResult || sigResult;
    const dirColor = d =>
        d === "LONG" || d === "FOLLOW_GAP_DOWN" || d === "FADE_GAP_DOWN" ? "var(--accent-up)"
            : d === "SHORT" || d === "FOLLOW_GAP_UP" || d === "FADE_GAP_UP" ? "var(--accent-down)"
                : "var(--text-muted)";

    return (
        <div style={{ minHeight: "calc(100vh - var(--navbar-height))", background: "var(--bg-primary)", color: "var(--text-primary)", fontFamily: "var(--font-body)" }}>
            <style>{`
                @keyframes ml-spin { to { transform: rotate(360deg); } }
                .ml-page { max-width: 1280px; margin: 0 auto; padding: 24px; display: flex; flex-direction: column; gap: 24px; }
                .ml-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; }
                .ml-stepper { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 12px; padding: 6px; }
                .ml-step-item { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 8px; cursor: pointer; transition: all 0.15s ease; border: 1px solid transparent; }
                .ml-step-item.active { background: var(--bg-tertiary); border-color: var(--accent-blue); }
                .ml-step-item.done { border-color: rgba(34,197,94,0.3); }
                .ml-drop { position: absolute; top: calc(100% + 4px); left: 0; right: 0; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--input-radius); z-index: 200; max-height: 230px; overflow-y: auto; box-shadow: var(--shadow-card-hover); }
                .ml-drop-item { padding: 8px 12px; font-size: 0.8rem; cursor: pointer; border-bottom: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center; }
                .ml-drop-item:hover { background: var(--bg-tertiary); }
                .ml-row-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
                .ml-ph-row { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border-subtle); font-size: 0.78rem; }
                .ml-prog-track { height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; flex: 1; }
                .ml-prog-fill { height: 100%; border-radius: 3px; background: var(--accent-blue,#3b82f6); transition: width .5s ease; }
                .ml-sig-box { padding: 16px; border-radius: var(--card-radius); border: 1.5px solid; text-align: center; }
                @media (max-width: 1024px) { .ml-stepper { grid-template-columns: repeat(3, 1fr); } }
                @media (max-width: 640px) { .ml-stepper { grid-template-columns: repeat(2, 1fr); } .ml-row-3 { grid-template-columns: 1fr; } }
            `}</style>

            <div className="ml-page">

                {/* ── Page Header & Title ── */}
                <div className="ml-header">
                    <div>
                        <div style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--accent-blue,#3b82f6)", marginBottom: 3 }}>
                            Quantitative Engine
                        </div>
                        <div style={{ fontSize: "1.4rem", fontWeight: 800, fontFamily: "var(--font-display)", color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                            Quant ML Strategy Engine
                        </div>
                    </div>

                    {/* View Mode Toggle & Reset State */}
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <button onClick={handleResetAllState} title="Clear saved progress and reset to default"
                            style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border-color)", background: "var(--bg-secondary)", color: "var(--text-muted)", fontSize: "0.78rem", fontWeight: 600, cursor: "pointer" }}>
                            Reset State
                        </button>

                        <div style={{ display: "flex", gap: 6, background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: 8, padding: 3 }}>
                            <button onClick={() => setViewMode("sequence")}
                                style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: viewMode === "sequence" ? "var(--accent-blue)" : "transparent", color: viewMode === "sequence" ? "#fff" : "var(--text-muted)", fontSize: "0.78rem", fontWeight: 600, cursor: "pointer" }}>
                                Sequence Step View
                            </button>
                            <button onClick={() => setViewMode("all")}
                                style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: viewMode === "all" ? "var(--accent-blue)" : "transparent", color: viewMode === "all" ? "#fff" : "var(--text-muted)", fontSize: "0.78rem", fontWeight: 600, cursor: "pointer" }}>
                                Full Pipeline Flow
                            </button>
                        </div>
                    </div>
                </div>

                {/* ── Symbol & Timeframe Target Bar ── */}
                <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: 12, padding: "14px 18px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 14, alignItems: "center" }}>
                    <Fld label="Target Symbol">
                        <div style={{ position: "relative" }}>
                            <Inp value={search} onChange={handleSearch} placeholder="Search NSE symbol (e.g. HDFCBANK)..." />
                            {searching && <div style={{ position: "absolute", right: 9, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}><Spinner sz={12} /></div>}
                            {searchResults.length > 0 && (
                                <div className="ml-drop">
                                    {searchResults.slice(0, 12).map(inst => (
                                        <div key={inst.instrument_key} className="ml-drop-item" onMouseDown={() => selectInstrument(inst)}>
                                            <span style={{ fontWeight: 600 }}>{inst.symbol}</span>
                                            <span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>{inst.exchange}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </Fld>

                    <Fld label="Global Pipeline Timeframe (LTF)" hint={`Sequence: ${timeframe} (LTF) ← ${mtf} (MTF) ← ${htf} (HTF)`}>
                        <div style={{ display: "flex", gap: 5 }}>
                            {TF_PRI.map(tf => <TfPill key={tf} tf={tf} active={timeframe === tf} onClick={handleGlobalTimeframeChange} />)}
                        </div>
                    </Fld>

                    <Fld label="HTF Filter Timeframe">
                        <Sel value={htf} onChange={setHtf} options={TF_PRI.map(v => ({ value: v, label: v }))} />
                    </Fld>

                    <Fld label="MTF Confirm Timeframe">
                        <Sel value={mtf} onChange={setMtf} options={TF_PRI.map(v => ({ value: v, label: v }))} />
                    </Fld>
                </div>

                {/* ── 5-Step Sequential Pipeline Progress Stepper ── */}
                <div className="ml-stepper">
                    {pipelineSteps.map(s => {
                        const active = currentStep === s.id;
                        return (
                            <div key={s.id} onClick={() => setCurrentStep(s.id)}
                                className={`ml-step-item ${active ? "active" : ""} ${s.done ? "done" : ""}`}>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                    <span style={{ fontSize: "0.68rem", fontWeight: 700, color: s.done ? "var(--accent-up)" : active ? "var(--accent-blue)" : "var(--text-muted)" }}>
                                        STEP {s.id}
                                    </span>
                                    {s.done ? <span style={{ fontSize: "0.75rem", color: "var(--accent-up)", fontWeight: 800 }}>✓</span> : null}
                                </div>
                                <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                    {s.title}
                                </div>
                                <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                    {s.desc}
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* ───────────────────────────────────────────────────────────── */}
                {/* STEP 1: MARKET PHASE CONTEXT LABELING                         */}
                {/* ───────────────────────────────────────────────────────────── */}
                {(viewMode === "all" || currentStep === 1) && (
                    <StepPanel stepNum={1} title="Step 1: Market Phase Context Labeling"
                        description="Label pre-computed indicators into market_context across timeframes."
                        badge={step1Done ? <Badge tone="up">LABELED</Badge> : null}
                        active={currentStep === 1} completed={step1Done}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.55 }}>
                                Run state machine labeling in sequence: <strong>15m → 5m → 3m → 1m</strong>. Reads pre-computed indicators from <code style={{ background: "var(--bg-tertiary)", padding: "0 3px", borderRadius: 3 }}>indicators</code> table and writes phase labels and phase reasons to PostgreSQL.
                            </p>
                            <Fld label="Target Timeframe" hint={`Synchronized with Global Pipeline Timeframe (${timeframe})`}>
                                <div style={{ display: "flex", gap: 6 }}>
                                    {TF_ALL.map(tf => {
                                        const r = labelResults[tf];
                                        const tick = (r?.market_rows > 0 || r?.status === "SUCCESS") ? " ✓" : r?.error ? " ✗" : "";
                                        return <TfPill key={tf} tf={tf} active={timeframe === tf} onClick={handleGlobalTimeframeChange} suffix={tick} />;
                                    })}
                                </div>
                            </Fld>

                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                                <Btn onClick={handleLabel} loading={labelLoading} disabled={!symbol} variant="primary">
                                    Label {timeframe} Market Context for {symbol || "Symbol"}
                                </Btn>
                                {viewMode === "sequence" && (
                                    <Btn onClick={() => setCurrentStep(2)} variant="secondary">
                                        Proceed to Step 2: Calculate Raw Outcomes →
                                    </Btn>
                                )}
                            </div>

                            {labelResults[timeframe] && (() => {
                                const r = labelResults[timeframe];
                                if (r._running) return <Alert type="info">Running state machine… 2–5 min for large datasets.</Alert>;
                                if (r.error) return <Alert type="error">{r.error}</Alert>;
                                return <Alert type="success"><strong>{r.market_rows?.toLocaleString()}</strong> market rows labeled · <strong>{r.rule_rows?.toLocaleString()}</strong> rule rows · {r.elapsed_sec}s</Alert>;
                            })()}

                            {Object.keys(labelResults).length > 0 && (
                                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    {TF_ALL.filter(tf => labelResults[tf]).map(tf => {
                                        const r = labelResults[tf];
                                        const ok = r?.market_rows > 0 || r?.status === "SUCCESS";
                                        return (
                                            <div key={tf} className="ml-ph-row">
                                                <span style={{ fontWeight: 700 }}>{tf}</span>
                                                {r._running ? <Badge tone="amber">RUNNING</Badge>
                                                    : r.error ? <Badge tone="down">ERROR</Badge>
                                                        : ok ? <Badge tone="up">{r.market_rows?.toLocaleString()} rows</Badge>
                                                            : <Badge tone="neutral">—</Badge>}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </StepPanel>
                )}

                {/* ───────────────────────────────────────────────────────────── */}
                {/* STEP 2: RAW BASELINE STRATEGY OUTCOMES                        */}
                {/* ───────────────────────────────────────────────────────────── */}
                {(viewMode === "all" || currentStep === 2) && (
                    <StepPanel stepNum={2} title="Step 2: Calculate Raw Strategy Outcomes"
                        description="Simulate baseline trade outcomes across history using default initial phase parameters."
                        badge={step2Done ? <Badge tone="up">{rawOutcomeResult.rows_written?.toLocaleString()} rows</Badge> : null}
                        active={currentStep === 2} completed={step2Done}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.55 }}>
                                First step in calibration sequence: Evaluates every labeled candle using <strong>default initial phase parameters</strong> to populate raw MFE, MAE, and trade observations into <code style={{ background: "var(--bg-tertiary)", padding: "0 3px", borderRadius: 3 }}>strategy_outcomes</code> table.
                            </p>

                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                                <Btn onClick={handleRawOutcomes} loading={rawOutcomeLoading} disabled={!symbol} variant="primary">
                                    Calculate Raw Baseline Outcomes for {symbol || "Symbol"} ({timeframe})
                                </Btn>
                                {viewMode === "sequence" && (
                                    <Btn onClick={() => setCurrentStep(3)} variant="secondary">
                                        Proceed to Step 3: MFE/MAE Calibration →
                                    </Btn>
                                )}
                            </div>

                            {rawOutcomeResult && (() => {
                                if (rawOutcomeResult.error) return <Alert type="error">{rawOutcomeResult.error}</Alert>;
                                if (rawOutcomeResult._running) return <Alert type="info">{rawOutcomeResult.message}</Alert>;
                                return (
                                    <Alert type="success">
                                        <strong>{rawOutcomeResult.rows_written?.toLocaleString()}</strong> baseline outcome rows generated · {rawOutcomeResult.elapsed_sec}s · ready for MFE/MAE parameter calibration
                                    </Alert>
                                );
                            })()}
                        </div>
                    </StepPanel>
                )}

                {/* ───────────────────────────────────────────────────────────── */}
                {/* STEP 3: MFE / MAE PARAMETER CALIBRATION                       */}
                {/* ───────────────────────────────────────────────────────────── */}
                {(viewMode === "all" || currentStep === 3) && (
                    <StepPanel stepNum={3} title="Step 3: MFE / MAE Phase Parameter Calibration"
                        description="Derive optimal Take-Profit (TP), Stop-Loss (SL), and Lookahead percentiles per market phase."
                        badge={step3Done ? <Badge tone="up">{calibResult.phases_calibrated} phases</Badge> : calibResult?.status === "NO_DATA" ? <Badge tone="amber">REQUIRES STEP 2</Badge> : null}
                        active={currentStep === 3} completed={step3Done}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.55 }}>
                                Analyzes historical baseline MFE/MAE distributions from Step 2 to derive optimal TP, SL, and lookahead parameters for <strong>{timeframe}</strong> and saves them to <code style={{ background: "var(--bg-tertiary)", padding: "0 3px", borderRadius: 3 }}>phase_params</code> table.
                            </p>

                            <div className="ml-row-3">
                                <Fld label="TP Percentile" hint="p60 → ~60% target">
                                    <Inp type="number" value={tpPct} onChange={v => setTpPct(Number(v))} />
                                </Fld>
                                <Fld label="SL Percentile" hint="p25 → 75% survive">
                                    <Inp type="number" value={slPct} onChange={v => setSlPct(Number(v))} />
                                </Fld>
                                <Fld label="Lookahead %ile" hint="p75 exit time">
                                    <Inp type="number" value={laPct} onChange={v => setLaPct(Number(v))} />
                                </Fld>
                            </div>

                            <Fld label="Min samples per phase" hint="Below this threshold, default parameters apply">
                                <Inp type="number" value={minSamples} onChange={v => setMinSamples(Number(v))} />
                            </Fld>

                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                                <Btn onClick={handleCalibrate} loading={calibLoading} disabled={!symbol} variant="success">
                                    Calibrate Optimal Phase Params from MFE/MAE
                                </Btn>
                                {viewMode === "sequence" && (
                                    <Btn onClick={() => setCurrentStep(4)} variant="secondary">
                                        Proceed to Step 4: Calculate Calibrated Outcomes →
                                    </Btn>
                                )}
                            </div>

                            {calibResult && (() => {
                                if (calibResult.error) return <Alert type="error">{calibResult.error}</Alert>;
                                if (calibResult.status === "NO_DATA") return (
                                    <Alert type="warn">
                                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                            <div><strong>No raw outcome data found.</strong> Run Step 2 first to generate baseline strategy outcomes for calibration.</div>
                                            <div>
                                                <Btn onClick={() => setCurrentStep(2)} variant="primary" size="sm">
                                                    Go to Step 2: Calculate Raw Outcomes
                                                </Btn>
                                            </div>
                                        </div>
                                    </Alert>
                                );
                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                        <Alert type="success">
                                            <strong>{calibResult.phases_calibrated}</strong> phases calibrated · <strong>{calibResult.phases_skipped_insufficient_data}</strong> skipped (&lt;{minSamples} samples)
                                            {calibResult.calibrated_from && <> · Window: <strong>{calibResult.calibrated_from.slice(0, 10)}</strong> to <strong>{calibResult.calibrated_to.slice(0, 10)}</strong></>}
                                        </Alert>
                                        {calibResult.phases && (
                                            <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 180, overflowY: "auto" }}>
                                                {Object.entries(calibResult.phases)
                                                    .filter(([, v]) => v.status === "CALIBRATED")
                                                    .sort((a, b) => (b[1].gross_rr || 0) - (a[1].gross_rr || 0))
                                                    .map(([phase, info]) => (
                                                        <div key={phase} className="ml-ph-row">
                                                            <span style={{ fontWeight: 600 }}>{phase}</span>
                                                            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                                                <span style={{ fontSize: "0.72rem", color: "var(--accent-up)" }}>TP {info.optimal_tp}</span>
                                                                <span style={{ fontSize: "0.72rem", color: "var(--accent-down)" }}>SL {info.optimal_sl}</span>
                                                                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{info.optimal_la_min}m</span>
                                                                {!info.viable && <Badge tone="down">WEAK</Badge>}
                                                            </div>
                                                        </div>
                                                    ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}
                        </div>
                    </StepPanel>
                )}

                {/* ───────────────────────────────────────────────────────────── */}
                {/* STEP 4: CALIBRATED STRATEGY OUTCOMES                          */}
                {/* ───────────────────────────────────────────────────────────── */}
                {(viewMode === "all" || currentStep === 4) && (
                    <StepPanel stepNum={4} title="Step 4: Calculate Calibrated Strategy Outcomes"
                        description="Re-simulate trade outcomes across history using newly calibrated optimal phase parameters."
                        badge={step4Done ? <Badge tone="up">{outcomeResult.rows_written?.toLocaleString()} rows</Badge> : null}
                        active={currentStep === 4} completed={step4Done}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.55 }}>
                                Final outcome evaluation step: Re-evaluates every candle using <strong>optimal calibrated TP/SL/lookahead parameters</strong> from Step 3, writing realistic R-multiples and outcomes to <code style={{ background: "var(--bg-tertiary)", padding: "0 3px", borderRadius: 3 }}>strategy_outcomes</code> for ML training.
                            </p>

                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
                                <Btn onClick={handleOutcomes} loading={outcomeLoading} disabled={!symbol} variant="primary">
                                    Calculate Calibrated Strategy Outcomes for {symbol || "Symbol"} ({timeframe})
                                </Btn>
                                {viewMode === "sequence" && (
                                    <Btn onClick={() => setCurrentStep(5)} variant="secondary">
                                        Proceed to Step 5: Model Training →
                                    </Btn>
                                )}
                            </div>

                            {outcomeResult && (() => {
                                if (outcomeResult.error) return <Alert type="error">{outcomeResult.error}</Alert>;
                                if (outcomeResult._running) return <Alert type="info">{outcomeResult.message}</Alert>;
                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                        <Alert type="success">
                                            <strong>{outcomeResult.rows_written?.toLocaleString()}</strong> strategy outcome rows calculated · {outcomeResult.elapsed_sec}s
                                            {outcomeResult.phases_calibrated > 0
                                                ? <> · <strong>{outcomeResult.phases_calibrated}</strong> calibrated phase parameters used</>
                                                : <span style={{ color: "#f59e0b" }}> · using defaults — complete Step 3 calibration first</span>}
                                        </Alert>
                                        {outcomeResult.params_overlap_warning && (
                                            <Alert type="warn">
                                                <strong>⚠ Calibration Window Overlap Warning:</strong> {outcomeResult.overlap_warning_details || "Evaluation request window overlaps the calibration window."}
                                            </Alert>
                                        )}
                                    </div>
                                );
                            })()}
                        </div>
                    </StepPanel>
                )}

                {/* ───────────────────────────────────────────────────────────── */}
                {/* STEP 5: MACHINE LEARNING MODEL TRAINING                       */}
                {/* ───────────────────────────────────────────────────────────── */}
                {(viewMode === "all" || currentStep === 5) && (
                    <StepPanel stepNum={5} title="Step 5: Machine Learning Model Training (LightGBM)"
                        description="Train multi-timeframe LightGBM classifier & regressor models."
                        badge={step5Done ? <Badge tone="up">Run #{modelRunId}</Badge> : null}
                        active={currentStep === 5} completed={step5Done}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                                <Btn onClick={handleTrain} loading={trainLoading} disabled={!symbol} variant="primary">
                                    Train LightGBM Model Pipeline ({timeframe} ← {mtf} ← {htf})
                                </Btn>
                                <Btn onClick={compareThresholds} loading={cmpLoading} disabled={!symbol || !modelRunId} variant="ghost" size="sm">
                                    Compare Thresholds
                                </Btn>
                                {viewMode === "sequence" && (
                                    <Btn onClick={() => setCurrentStep(6)} variant="secondary">
                                        Proceed to Step 6: Paper Trade & Signals →
                                    </Btn>
                                )}
                            </div>

                            {trainResults?.error && <Alert type="error">{trainResults.error}</Alert>}

                            {trainResults && !trainResults.error && (
                                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                                    <div className="ml-row-3">
                                        <Stat label="Walk-fwd AUC" value={trainResults.wf_auc_mean?.toFixed(4)}
                                            tone={trainResults.wf_auc_mean > 0.57 ? "up" : trainResults.wf_auc_mean < 0.52 ? "down" : undefined}
                                            sub={trainResults.wf_auc_mean > 0.60 ? "✓ Strong Signal" : trainResults.wf_auc_mean < 0.55 ? "⚠ Marginal" : "Acceptable"} />
                                        <Stat label="Walk-fwd MAE" value={trainResults.wf_mae_mean?.toFixed(4)} />
                                        <Stat label="Rows Trained" value={trainResults.rows_trained?.toLocaleString()} />
                                    </div>

                                    {trainResults.phase_analysis && Object.keys(trainResults.phase_analysis).length > 0 && (
                                        <div>
                                            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>
                                                Phase Analysis — Sorted by Expected R-Multiple
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 220, overflowY: "auto" }}>
                                                {Object.entries(trainResults.phase_analysis)
                                                    .sort((a, b) => (b[1].expected_r_at_threshold || 0) - (a[1].expected_r_at_threshold || 0))
                                                    .map(([phase, info]) => (
                                                        <div key={phase} className="ml-ph-row">
                                                            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{phase}</span>
                                                            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                                                                <Badge tone={info.exec_class === "SKIP" ? "neutral" : "blue"}>{info.exec_class}</Badge>
                                                                <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>n={info.samples}</span>
                                                                <span style={{ fontWeight: 700, color: info.avg_r > 0 ? "var(--accent-up)" : "var(--accent-down)" }}>
                                                                    {info.avg_r > 0 ? "+" : ""}{info.avg_r?.toFixed(3)}R
                                                                </span>
                                                            </div>
                                                        </div>
                                                    ))}
                                            </div>
                                        </div>
                                    )}

                                    {cmpResult && <Alert type="info">{cmpResult.instruction || "Threshold comparison complete."}</Alert>}
                                </div>
                            )}
                        </div>
                    </StepPanel>
                )}

                {/* ───────────────────────────────────────────────────────────── */}
                {/* STEP 6: PAPER TRADING, BACKTEST & LIVE EXECUTION SIGNALS     */}
                {/* ───────────────────────────────────────────────────────────── */}
                {(viewMode === "all" || currentStep === 6) && (
                    <StepPanel stepNum={6} title="Step 6: Paper Trading, Backtest & Real-Time Execution Signals"
                        description="Simulate leverage trading backtests and generate real-time execution signals."
                        badge={step6Done ? <Badge tone="up">COMPLETE</Badge> : null}
                        active={currentStep === 6} completed={step6Done}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

                            {/* Section 5A: Real-Time Signal Generator */}
                            <div style={{ background: "var(--bg-tertiary)", borderRadius: 10, padding: 14, border: "1px solid var(--border-subtle)" }}>
                                <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>
                                    ⚡ Real-Time Signal Generator
                                </div>
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
                                    <Fld label="LTF Model Run ID" hint="Auto-filled after Step 4 training">
                                        <Inp value={runIdLtf} onChange={setRunIdLtf} placeholder="e.g. 42" />
                                    </Fld>
                                    <Fld label="Signal Win Threshold" hint="Min confidence (default 0.60)">
                                        <Inp type="number" step="0.05" value={threshold} onChange={v => setThreshold(Number(v))} />
                                    </Fld>
                                </div>

                                <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                                    <Btn size="sm" onClick={handlePredictSignal} loading={sigLoading} disabled={!symbol || !runIdLtf}>
                                        Predict Single TF Signal
                                    </Btn>
                                    <Btn size="sm" variant="secondary" onClick={handleHtfSignal} loading={htfSigLoading} disabled={!symbol || !runIdLtf}>
                                        Predict HTF 3-Stage Pipeline Signal
                                    </Btn>
                                </div>

                                {activeSig && (() => {
                                    if (activeSig.error) return <Alert type="error">{activeSig.error}</Alert>;
                                    if (activeSig.status === "NO_SIGNAL") return <Alert type="info">No signal — phase mapped to SKIP</Alert>;
                                    const prob = activeSig.combined_prob ?? activeSig.win_prob ?? 0;
                                    const dir = activeSig.direction;
                                    const ec = activeSig.ltf_exec_class ?? activeSig.exec_class;
                                    const dc = dirColor(dir);
                                    return (
                                        <div className="ml-sig-box" style={{ borderColor: dc, background: `${dc}0d` }}>
                                            <div style={{ fontSize: "1.2rem", fontWeight: 800, color: dc, letterSpacing: ".04em", marginBottom: 2 }}>{dir}</div>
                                            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 8 }}>{ec}</div>
                                            <div style={{ display: "flex", justifyContent: "center", gap: 24 }}>
                                                <div>
                                                    <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>WIN PROB</div>
                                                    <div style={{ fontSize: "1rem", fontWeight: 700, color: prob > .6 ? "var(--accent-up)" : "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>{(prob * 100).toFixed(1)}%</div>
                                                </div>
                                                <div>
                                                    <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>TP / SL</div>
                                                    <div style={{ fontSize: "1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{activeSig.tp_atr}R / {activeSig.sl_atr}R</div>
                                                </div>
                                                {activeSig.size_multiplier !== undefined && (
                                                    <div>
                                                        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>SIZE</div>
                                                        <div style={{ fontSize: "1rem", fontWeight: 700, color: activeSig.size_multiplier < 1 ? "#f59e0b" : "var(--text-primary)" }}>{activeSig.size_multiplier}×</div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })()}
                            </div>

                            {/* Section 5B: Paper Trading Simulation */}
                            <div style={{ background: "var(--bg-tertiary)", borderRadius: 10, padding: 14, border: "1px solid var(--border-subtle)" }}>
                                <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 10 }}>
                                    📈 Paper Trading Simulation & Equity Curve
                                </div>
                                <div className="ml-row-3" style={{ marginBottom: 12 }}>
                                    <Fld label="Starting Capital (₹)">
                                        <Inp type="number" value={startCap} onChange={v => setStartCap(Number(v))} />
                                    </Fld>
                                    <Fld label="Margin / Share (₹)">
                                        <Inp type="number" value={marginPS} onChange={v => setMarginPS(Number(v))} />
                                    </Fld>
                                    <Fld label="Min Win Threshold">
                                        <Inp type="number" value={threshold} step="0.05" onChange={v => setThreshold(Number(v))} />
                                    </Fld>
                                </div>

                                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                                    <Btn onClick={runPaperTrading} loading={paperLoading} disabled={!symbol || !modelRunId} variant="primary">
                                        Run Simulation
                                    </Btn>
                                    {paperLoading && (
                                        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
                                            <div className="ml-prog-track">
                                                <div className="ml-prog-fill" style={{ width: `${paperPercent}%` }} />
                                            </div>
                                            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{paperPercent}%</span>
                                        </div>
                                    )}
                                </div>

                                {paperResult && !paperResult.error && (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                                        <div className="ml-row-3">
                                            <Stat label="Final Capital" value={`₹${paperResult.final_capital?.toLocaleString()}`} tone={paperResult.net_pnl > 0 ? "up" : "down"} />
                                            <Stat label="Net P&L" value={`${paperResult.net_pnl > 0 ? "+" : ""}${paperResult.net_pnl_pct?.toFixed(2)}%`} tone={paperResult.net_pnl > 0 ? "up" : "down"} />
                                            <Stat label="Win Rate" value={`${(paperResult.win_rate * 100).toFixed(1)}%`} tone={paperResult.win_rate > 0.50 ? "up" : undefined} />
                                            <Stat label="Expectancy" value={`${paperResult.expectancy_r > 0 ? "+" : ""}${paperResult.expectancy_r?.toFixed(3)}R`} tone={paperResult.expectancy_r > 0 ? "up" : "down"} />
                                            <Stat label="Max Drawdown" value={`${paperResult.max_drawdown_pct?.toFixed(2)}%`} tone={paperResult.max_drawdown_pct > 20 ? "down" : undefined} />
                                            <Stat label="Total Trades" value={paperResult.total_trades} />
                                        </div>

                                        {/* Equity Curve Graph */}
                                        {equityCurve.length >= 2 && (() => {
                                            const vals = equityCurve.map(p => p.capital ?? p.capital_after ?? 0);
                                            const mn = Math.min(...vals);
                                            const mx = Math.max(...vals);
                                            const rng = mx - mn || 1;
                                            const W = equityCurve.length - 1;
                                            const pts = vals.map((v, i) => `${i},${78 - ((v - mn) / rng) * 70}`).join(" ");
                                            const up = vals[vals.length - 1] >= vals[0];
                                            const lc = up ? "var(--accent-up)" : "var(--accent-down)";
                                            return (
                                                <div style={{ background: "var(--bg-secondary)", borderRadius: 8, padding: 12, border: "1px solid var(--border-subtle)" }}>
                                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                                                        <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-muted)" }}>Equity Curve ({equityCurve.length} trades)</span>
                                                        <span style={{ fontSize: "0.85rem", fontWeight: 700, color: lc, fontVariantNumeric: "tabular-nums" }}>
                                                            {up ? "+" : ""}₹{(vals[vals.length - 1] - vals[0]).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                                        </span>
                                                    </div>
                                                    <svg width="100%" height="90" viewBox={`0 0 ${W} 80`} preserveAspectRatio="none"
                                                        style={{ display: "block", background: "var(--bg-tertiary)", borderRadius: 6 }}>
                                                        <polyline points={pts} fill="none" stroke={lc} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
                                                    </svg>
                                                </div>
                                            );
                                        })()}
                                    </div>
                                )}
                            </div>

                        </div>
                    </StepPanel>
                )}

            </div>
        </div>
    );
}
