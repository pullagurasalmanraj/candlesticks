// MLTrainingPage.jsx
// Redesigned with new endpoints:
//   POST /api/offline/label-market-context       (per-TF, 15m→3m→1m)
//   POST /api/offline/calibrate-phase-params     (NEW — derives TP/SL from MFE/MAE)
//   POST /api/offline/calc-strategy-outcomes     (reads phase_params table)
//   POST /api/train-pipeline                     (htf/mtf params, new response shape)
//   POST /api/paper-trade/run                    (updated params + response)
//   GET  /api/paper-trade/equity-curve
//   GET  /api/market-context/rule-stats
//   POST /api/live/predict-signal                (NEW — single TF signal)
//   POST /api/live/predict-signal-htf            (NEW — 3-stage hierarchical signal)
// ──────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect, useRef } from "react";
import { useTheme } from "../context/ThemeContext";

// ─── tiny design tokens ──────────────────────────────────────────────────────
const T = {
    xs: "0.64rem", sm: "0.71rem", md: "0.78rem", lg: "0.88rem",
    r: { sm: 5, md: 7, lg: 10 },
};

// ─── micro atoms ─────────────────────────────────────────────────────────────
const Spinner = ({ sz = 13 }) => (
    <svg width={sz} height={sz} viewBox="0 0 24 24" fill="none"
        style={{ animation: "ml-spin .75s linear infinite", flexShrink: 0 }}>
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="42 14" />
    </svg>
);

const Badge = ({ children, tone = "neutral" }) => {
    const map = {
        neutral: ["var(--bg-tertiary)",        "var(--text-muted)",              "var(--border-subtle)"],
        up:      ["rgba(34,197,94,.12)",        "var(--accent-up)",               "rgba(34,197,94,.28)"],
        down:    ["rgba(239,68,68,.12)",        "var(--accent-down)",             "rgba(239,68,68,.28)"],
        blue:    ["rgba(59,130,246,.12)",       "var(--accent-blue,#3b82f6)",     "rgba(59,130,246,.28)"],
        amber:   ["rgba(245,158,11,.12)",       "#f59e0b",                        "rgba(245,158,11,.28)"],
    };
    const [bg, color, border] = map[tone] || map.neutral;
    return (
        <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 7px", borderRadius: 4, fontSize: T.xs, fontWeight: 700, letterSpacing: ".05em", background: bg, color, border: `1px solid ${border}`, whiteSpace: "nowrap" }}>
            {children}
        </span>
    );
};

const Btn = ({ children, onClick, loading, disabled, variant = "primary", size = "md" }) => {
    const pad   = size === "sm" ? "4px 10px" : "7px 16px";
    const fz    = size === "sm" ? T.xs : T.sm;
    const styles = {
        primary:   { bg: "var(--accent-blue,#3b82f6)", color: "#fff",                      border: "transparent" },
        secondary: { bg: "var(--bg-tertiary)",          color: "var(--text-primary)",        border: "var(--border-color)" },
        ghost:     { bg: "transparent",                 color: "var(--text-muted)",           border: "var(--border-subtle)" },
        success:   { bg: "var(--accent-up)",            color: "#fff",                       border: "transparent" },
        danger:    { bg: "rgba(239,68,68,.1)",          color: "var(--accent-down)",          border: "rgba(239,68,68,.3)" },
    };
    const v   = styles[variant] || styles.primary;
    const off = disabled || loading;
    return (
        <button disabled={off} onClick={onClick}
            style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: pad, borderRadius: T.r.sm, border: `1px solid ${v.border}`, background: v.bg, color: v.color, fontSize: fz, fontWeight: 600, cursor: off ? "not-allowed" : "pointer", opacity: off ? .45 : 1, transition: "opacity .15s", whiteSpace: "nowrap" }}>
            {loading && <Spinner sz={11} />}{children}
        </button>
    );
};

const Lbl = ({ children }) => (
    <span style={{ fontSize: T.xs, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>{children}</span>
);

const Inp = ({ value, onChange, placeholder, type = "text", step }) => (
    <input value={value} type={type} step={step} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        style={{ width: "100%", boxSizing: "border-box", padding: "6px 10px", borderRadius: T.r.sm, background: "var(--bg-input,var(--bg-tertiary))", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: T.md, outline: "none" }} />
);

const Sel = ({ value, onChange, options }) => (
    <select value={value} onChange={e => onChange(e.target.value)}
        style={{ width: "100%", boxSizing: "border-box", padding: "6px 10px", borderRadius: T.r.sm, background: "var(--bg-input,var(--bg-tertiary))", border: "1px solid var(--border-color)", color: "var(--text-primary)", fontSize: T.md, outline: "none" }}>
        {options.map(o => <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? o}</option>)}
    </select>
);

const Fld = ({ label, hint, children }) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {label && <Lbl>{label}</Lbl>}
        {children}
        {hint && <span style={{ fontSize: T.xs, color: "var(--text-muted)" }}>{hint}</span>}
    </div>
);

const Panel = ({ title, badge, children, style: s }) => (
    <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: T.r.lg, overflow: "hidden", ...s }}>
        {title && (
            <div style={{ padding: "9px 14px", borderBottom: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: T.xs, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: "var(--text-muted)" }}>{title}</span>
                {badge}
            </div>
        )}
        <div style={{ padding: 14 }}>{children}</div>
    </div>
);

const Alert = ({ type = "info", children }) => {
    const c = { info: "var(--accent-blue,#3b82f6)", error: "var(--accent-down)", success: "var(--accent-up)", warn: "#f59e0b" }[type] || "#3b82f6";
    return <div style={{ padding: "7px 11px", borderRadius: T.r.sm, background: `${c}11`, border: `1px solid ${c}30`, fontSize: T.xs, color: c, lineHeight: 1.55 }}>{children}</div>;
};

const Stat = ({ label, value, tone, sub }) => {
    const color = tone === "up" ? "var(--accent-up)" : tone === "down" ? "var(--accent-down)" : "var(--text-primary)";
    return (
        <div style={{ background: "var(--bg-tertiary)", borderRadius: T.r.sm, padding: "8px 10px", textAlign: "center" }}>
            <div style={{ fontSize: T.xs, color: "var(--text-muted)", marginBottom: 3 }}>{label}</div>
            <div style={{ fontSize: T.lg, fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>{value ?? "—"}</div>
            {sub && <div style={{ fontSize: T.xs, color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>}
        </div>
    );
};

const PhaseRow = ({ children }) => (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: "1px solid var(--border-subtle)", fontSize: T.sm }}>
        {children}
    </div>
);

const TfPill = ({ tf, active, onClick, suffix }) => (
    <button onClick={() => onClick(tf)}
        style={{ padding: "3px 10px", borderRadius: 5, border: `1px solid ${active ? "var(--accent-blue,#3b82f6)" : "var(--border-color)"}`, background: active ? "var(--accent-blue,#3b82f6)" : "var(--bg-tertiary)", color: active ? "#fff" : "var(--text-muted)", fontSize: T.xs, fontWeight: 700, cursor: "pointer", transition: "all .12s" }}>
        {tf}{suffix || ""}
    </button>
);

// ─── constants ───────────────────────────────────────────────────────────────
const TF_PRI = ["1m", "3m", "5m", "15m"];
const TF_ALL = ["15m", "5m", "3m", "1m"];   // label order: top-down

// ─── page ────────────────────────────────────────────────────────────────────
export default function MLTrainingPage() {
    const { theme } = useTheme();

    // Step 1 — symbol
    const [symbol,        setSymbol]       = useState("");
    const [search,        setSearch]       = useState("");
    const [searching,     setSearching]    = useState(false);
    const [searchResults, setSearchResults]= useState([]);
    const [timeframe,     setTimeframe]    = useState("3m");
    const [htf,           setHtf]          = useState("15m");
    const [mtf,           setMtf]          = useState("5m");

    // Step 2 — data pipeline
    const [convertLoading, setConvertLoading] = useState(false);
    const [convertMsg,     setConvertMsg]     = useState("");

    // Step 3 — label (per TF)
    const [labelTf,      setLabelTf]      = useState("15m");
    const [labelLoading, setLabelLoading] = useState(false);
    const [labelResults, setLabelResults] = useState({});   // { "15m": {...}, ... }

    // Step 4 — calibrate
    const [calibTf,          setCalibTf]          = useState("3m");
    const [calibLoading,     setCalibrateLoading]  = useState(false);
    const [calibResult,      setCalibrateResult]   = useState(null);
    const [tpPct,            setTpPct]             = useState(60);
    const [slPct,            setSlPct]             = useState(25);
    const [laPct,            setLaPct]             = useState(75);
    const [minSamples,       setMinSamples]        = useState(30);

    // Step 5 — outcomes
    const [outcomeLoading, setOutcomeLoading] = useState(false);
    const [outcomeResult,  setOutcomeResult]  = useState(null);

    // Step 6 — train
    const [trainLoading, setTrainLoading] = useState(false);
    const [trainResults, setTrainResults] = useState(null);
    const [modelRunId,   setModelRunId]   = useState(null);

    // rule stats
    const [ruleStats,        setRuleStats]        = useState(null);
    const [ruleStatsLoading, setRuleStatsLoading] = useState(false);

    // live signal
    const [runIdLtf,      setRunIdLtf]      = useState("");
    const [runIdMtf,      setRunIdMtf]      = useState("");
    const [runIdHtf,      setRunIdHtf]      = useState("");
    const [sigLoading,    setSigLoading]    = useState(false);
    const [sigResult,     setSigResult]     = useState(null);
    const [htfSigLoading, setHtfSigLoading] = useState(false);
    const [htfSigResult,  setHtfSigResult]  = useState(null);

    // Step 7 — paper trade
    const [paperLoading,  setPaperLoading]  = useState(false);
    const [paperResult,   setPaperResult]   = useState(null);
    const [paperPercent,  setPaperPercent]  = useState(0);
    const [paperProgress, setPaperProgress] = useState("");
    const [threshold,     setThreshold]     = useState(0.60);
    const [startCap,      setStartCap]      = useState(100000);
    const [marginPS,      setMarginPS]      = useState(21.68);
    const [equityCurve,   setEquityCurve]   = useState([]);
    const [equityLoading, setEquityLoading] = useState(false);

    // compare thresholds
    const [cmpLoading, setCmpLoading] = useState(false);
    const [cmpResult,  setCmpResult]  = useState(null);

    // refs
    const searchAbortRef  = useRef(null);
    const latestSearchRef = useRef("");
    const justSelectedRef = useRef(false);
    const paperTimerRef   = useRef(null);

    // ── instrument search ────────────────────────────────────────────────────
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
                const res  = await fetch(`/api/instruments?q=${encodeURIComponent(q)}`, { signal: ctrl.signal });
                const data = await res.json();
                if (latestSearchRef.current !== q) return;
                const uniq = Array.isArray(data.instruments)
                    ? Array.from(new Map(data.instruments.filter(i => i?.instrument_key).map(i => [i.instrument_key, i])).values())
                    : [];
                setSearchResults(uniq);
            } catch (e) { if (e.name !== "AbortError") setSearchResults([]); }
            finally    { if (latestSearchRef.current === q) setSearching(false); }
        }, 220);
        return () => { clearTimeout(tid); ctrl.abort(); };
    }, [search]);

    // ── handlers ─────────────────────────────────────────────────────────────
    const handleSearch = v => { const u = v.toUpperCase(); setSymbol(u); setSearch(u); };

    const selectInstrument = inst => {
        justSelectedRef.current = true;
        setSymbol(inst.symbol); setSearch(inst.symbol); setSearchResults([]);
        if (searchAbortRef.current) searchAbortRef.current.abort();
    };

    // Step 2
    const handleConvertTicks = async () => {
        if (!symbol) return alert("Select a symbol first");
        setConvertLoading(true); setConvertMsg("");
        try {
            const mapData = await (await fetch(`/api/symbol-feedkey?symbol=${symbol}`)).json();
            const json    = await (await fetch("/api/start-live-conversion", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, feed_key: mapData.feed_key }),
            })).json();
            setConvertMsg(
                json.status === "STARTED"         ? `✓ Live conversion started — ${symbol}`
                : json.status === "ALREADY_RUNNING" ? `ℹ Conversion already running for ${symbol}`
                : JSON.stringify(json)
            );
        } catch (e) { setConvertMsg("Error: " + e.message); }
        setConvertLoading(false);
    };

    // Step 3
    const handleLabel = async () => {
        if (!symbol) return alert("Select a symbol first");
        const tf = labelTf;
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

    // Step 4
    const handleCalibrate = async () => {
        if (!symbol) return alert("Select a symbol first");
        setCalibrateLoading(true); setCalibrateResult(null);
        try {
            const res = await fetch("/api/offline/calibrate-phase-params", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe: calibTf, tp_percentile: tpPct, sl_percentile: slPct, la_percentile: laPct, min_samples: minSamples }),
            });
            setCalibrateResult(await res.json());
        } catch (e) { setCalibrateResult({ error: e.message }); }
        setCalibrateLoading(false);
    };

    // Step 5
    const handleOutcomes = async () => {
        if (!symbol) return alert("Select a symbol first");
        setOutcomeLoading(true);
        setOutcomeResult({ _running: true, message: "Computing outcomes with calibrated params…" });
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

    // Step 6
    const handleTrain = async () => {
        if (!symbol) return alert("Select a symbol first");
        setTrainLoading(true); setTrainResults(null); setModelRunId(null);
        try {
            const res  = await fetch("/api/train-pipeline", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, timeframe, htf, mtf }),
            });
            const data = await res.json();
            if (data.status !== "SUCCESS") throw new Error(data.error || "Training failed");
            setModelRunId(data.model_run_id);
            setRunIdLtf(String(data.model_run_id || ""));  // auto-fill signal ID
            setTrainResults(data);
        } catch (e) { setTrainResults({ error: e.message }); }
        setTrainLoading(false);
    };

    const fetchRuleStats = async () => {
        if (!symbol) return;
        setRuleStatsLoading(true);
        try {
            const res = await fetch(`/api/market-context/rule-stats?symbol=${symbol}&timeframe=${timeframe}`);
            setRuleStats(await res.json());
        } catch (e) { console.error(e); }
        setRuleStatsLoading(false);
    };

    // Live signal — single TF
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

    // Live signal — HTF pipeline
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

    // Paper trade
    const fakeProg = () => {
        let p = 5; setPaperPercent(5);
        paperTimerRef.current = setInterval(() => {
            p += Math.random() * 7;
            if (p >= 90) { p = 90; clearInterval(paperTimerRef.current); }
            setPaperPercent(Math.floor(p));
        }, 700);
    };

    const runPaperTrading = async () => {
        if (!symbol)     return alert("Select a symbol first");
        if (!modelRunId) return alert("Train a model first (Step 6)");
        setPaperLoading(true); setPaperResult(null); setEquityCurve([]);
        setPaperProgress("Initialising paper trading engine…"); fakeProg();
        try {
            setPaperProgress("Running leverage-based trade simulation…");
            const res  = await fetch("/api/paper-trade/run", {
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

    // ── derived ──────────────────────────────────────────────────────────────
    const labelDone  = Object.values(labelResults).some(r => r?.market_rows > 0 || r?.status === "SUCCESS");
    const calibDone  = calibResult?.phases_calibrated > 0;
    const outcomeDone = outcomeResult?.status === "SUCCESS";
    const trainDone  = !!modelRunId;
    const paperDone  = paperResult && !paperResult.error;

    const steps = [
        { id: 1, label: "Symbol",        done: !!symbol },
        { id: 2, label: "Data Pipeline", done: !!convertMsg && !convertMsg.includes("Error") },
        { id: 3, label: "Label Context", done: labelDone },
        { id: 4, label: "Calibrate",     done: calibDone },
        { id: 5, label: "Outcomes",      done: outcomeDone },
        { id: 6, label: "Train Model",   done: trainDone },
        { id: 7, label: "Paper Trade",   done: paperDone },
    ];

    const activeSig = htfSigResult || sigResult;
    const dirColor  = d =>
        d === "LONG"  || d === "FOLLOW_GAP_DOWN" || d === "FADE_GAP_DOWN"  ? "var(--accent-up)"
      : d === "SHORT" || d === "FOLLOW_GAP_UP"   || d === "FADE_GAP_UP"    ? "var(--accent-down)"
      : "var(--text-muted)";

    // ── render ────────────────────────────────────────────────────────────────
    return (
        <div style={{ minHeight: "calc(100vh - var(--navbar-height))", background: "var(--bg-primary)", color: "var(--text-primary)", fontFamily: "var(--font-body)" }}>
            <style>{`
                @keyframes ml-spin { to { transform: rotate(360deg); } }
                .ml-page  { max-width:1400px; margin:0 auto; padding:20px var(--content-padding,20px); display:flex; flex-direction:column; gap:16px; }

                /* Pipeline bar */
                .ml-pipeline { display:flex; align-items:stretch; background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:10px; overflow:hidden; }
                .ml-step     { flex:1; display:flex; align-items:center; gap:7px; padding:10px 14px; font-size:0.70rem; font-weight:600; color:var(--text-muted); border-right:1px solid var(--border-subtle); white-space:nowrap; transition:color .15s; }
                .ml-step:last-child { border-right:none; }
                .ml-step.done   { color:var(--accent-up); }
                .ml-step.active { color:var(--text-primary); }
                .ml-step-num { width:20px; height:20px; border-radius:50%; border:1.5px solid currentColor; display:flex; align-items:center; justify-content:center; font-size:0.58rem; font-weight:700; flex-shrink:0; }
                .ml-step.done .ml-step-num { background:var(--accent-up); border-color:var(--accent-up); color:#fff; }

                /* Layout */
                .ml-layout { display:grid; grid-template-columns:300px 1fr; gap:16px; align-items:start; }
                .ml-rail   { display:flex; flex-direction:column; gap:10px; min-width:0; }
                .ml-right  { display:flex; flex-direction:column; gap:14px; min-width:0; }
                .ml-row-2  { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
                .ml-row-3  { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; }

                /* Search dropdown */
                .ml-drop { position:absolute; top:calc(100% + 4px); left:0; right:0; background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:8px; z-index:200; max-height:230px; overflow-y:auto; box-shadow:0 8px 28px rgba(0,0,0,.22); }
                .ml-drop-item { padding:8px 12px; font-size:0.74rem; cursor:pointer; border-bottom:1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center; }
                .ml-drop-item:hover { background:var(--bg-tertiary); }

                /* Misc */
                .ml-tf-row  { display:flex; gap:5px; flex-wrap:wrap; }
                .ml-ph-row  { display:flex; justify-content:space-between; align-items:center; padding:4px 0; border-bottom:1px solid var(--border-subtle); font-size:0.70rem; }
                .ml-prog-track { height:5px; background:var(--bg-tertiary); border-radius:3px; overflow:hidden; flex:1; }
                .ml-prog-fill  { height:100%; border-radius:3px; background:var(--accent-blue,#3b82f6); transition:width .5s ease; }
                .ml-sig-box    { padding:14px; border-radius:8px; border:1.5px solid; text-align:center; }

                @media (max-width:1100px) { .ml-layout { grid-template-columns:1fr; } .ml-row-2,.ml-row-3 { grid-template-columns:1fr; } }
                @media (max-width:700px)  { .ml-pipeline { flex-wrap:wrap; } .ml-step { flex:none; width:50%; border-bottom:1px solid var(--border-subtle); } }
            `}</style>

            <div className="ml-page">

                {/* ── Pipeline bar ── */}
                <div className="ml-pipeline">
                    {steps.map(s => (
                        <div key={s.id} className={`ml-step ${s.done ? "done" : "active"}`}>
                            <span className="ml-step-num">{s.done ? "✓" : s.id}</span>
                            {s.label}
                        </div>
                    ))}
                </div>

                <div className="ml-layout">

                    {/* ══════════════ LEFT RAIL ══════════════ */}
                    <div className="ml-rail">

                        {/* 1 — Symbol */}
                        <Panel title="Symbol & Timeframes" badge={symbol ? <Badge tone="blue">{symbol}</Badge> : null}>
                            <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                                <Fld label="Stock symbol">
                                    <div style={{ position:"relative" }}>
                                        <Inp value={search} onChange={handleSearch} placeholder="Search NSE symbol…" />
                                        {searching && <div style={{ position:"absolute", right:9, top:"50%", transform:"translateY(-50%)", color:"var(--text-muted)" }}><Spinner sz={12} /></div>}
                                        {searchResults.length > 0 && (
                                            <div className="ml-drop">
                                                {searchResults.slice(0, 12).map(inst => (
                                                    <div key={inst.instrument_key} className="ml-drop-item" onMouseDown={() => selectInstrument(inst)}>
                                                        <span style={{ fontWeight:600 }}>{inst.symbol}</span>
                                                        <span style={{ color:"var(--text-muted)", fontSize:"0.65rem" }}>{inst.exchange}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </Fld>

                                <Fld label="Primary timeframe">
                                    <div className="ml-tf-row">
                                        {TF_PRI.map(tf => <TfPill key={tf} tf={tf} active={timeframe === tf} onClick={setTimeframe} />)}
                                    </div>
                                </Fld>

                                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                                    <Fld label="HTF filter" hint="15m recommended">
                                        <Sel value={htf} onChange={setHtf} options={TF_PRI.map(v => ({ value:v, label:v }))} />
                                    </Fld>
                                    <Fld label="MTF confirm" hint="5m recommended">
                                        <Sel value={mtf} onChange={setMtf} options={TF_PRI.map(v => ({ value:v, label:v }))} />
                                    </Fld>
                                </div>

                                <p style={{ fontSize:T.xs, color:"var(--text-muted)", margin:0, lineHeight:1.55 }}>
                                    HTF features joined via <code style={{ background:"var(--bg-tertiary)", padding:"0 3px", borderRadius:3 }}>merge_asof</code> — strictly no look-ahead.
                                </p>
                            </div>
                        </Panel>

                        {/* 2 — Data Pipeline */}
                        <Panel title="Data Pipeline" badge={convertMsg && !convertMsg.includes("Error") ? <Badge tone="up">LIVE</Badge> : null}>
                            <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                                <p style={{ fontSize:T.xs, color:"var(--text-muted)", margin:0 }}>Start live tick → candle conversion before labelling.</p>
                                <Btn onClick={handleConvertTicks} loading={convertLoading} disabled={!symbol} variant="secondary">Start live conversion</Btn>
                                {convertMsg && <Alert type={convertMsg.includes("Error") ? "error" : convertMsg.includes("already") ? "info" : "success"}>{convertMsg}</Alert>}
                            </div>
                        </Panel>

                        {/* 3 — Label Context */}
                        <Panel title="Label Market Context" badge={labelDone ? <Badge tone="up">DONE</Badge> : null}>
                            <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                                <p style={{ fontSize:T.xs, color:"var(--text-muted)", margin:0, lineHeight:1.55 }}>
                                    Run in order: <strong>15m → 5m → 3m → 1m</strong>. Each writes to <code style={{ background:"var(--bg-tertiary)", padding:"0 3px", borderRadius:3 }}>market_context</code>.
                                </p>
                                <Fld label="Timeframe to label">
                                    <div className="ml-tf-row">
                                        {TF_ALL.map(tf => {
                                            const r    = labelResults[tf];
                                            const tick = (r?.market_rows > 0 || r?.status === "SUCCESS") ? " ✓" : r?.error ? " ✗" : "";
                                            return <TfPill key={tf} tf={tf} active={labelTf === tf} onClick={setLabelTf} suffix={tick} />;
                                        })}
                                    </div>
                                </Fld>
                                <Btn onClick={handleLabel} loading={labelLoading} disabled={!symbol}>Label {labelTf} context</Btn>

                                {labelResults[labelTf] && (() => {
                                    const r = labelResults[labelTf];
                                    if (r._running) return <Alert type="info">Running… 2–5 min for large datasets.</Alert>;
                                    if (r.error)    return <Alert type="error">{r.error}</Alert>;
                                    return <Alert type="success"><strong>{r.market_rows?.toLocaleString()}</strong> rows labelled · <strong>{r.rule_rows?.toLocaleString()}</strong> rule rows · {r.elapsed_sec}s</Alert>;
                                })()}

                                {Object.keys(labelResults).length > 0 && (
                                    <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
                                        {TF_ALL.filter(tf => labelResults[tf]).map(tf => {
                                            const r  = labelResults[tf];
                                            const ok = r?.market_rows > 0 || r?.status === "SUCCESS";
                                            return (
                                                <div key={tf} className="ml-ph-row">
                                                    <span style={{ fontWeight:700 }}>{tf}</span>
                                                    {r._running ? <Badge tone="amber">RUNNING</Badge>
                                                     : r.error  ? <Badge tone="down">ERROR</Badge>
                                                     : ok       ? <Badge tone="up">{r.market_rows?.toLocaleString()} rows</Badge>
                                                     :            <Badge tone="neutral">—</Badge>}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </Panel>

                        {/* 4 — Calibrate Phase Params (NEW) */}
                        <Panel title="Calibrate TP / SL / Lookahead"
                            badge={calibDone ? <Badge tone="up">{calibResult.phases_calibrated} phases</Badge>
                                 : calibResult?.status === "NO_DATA" ? <Badge tone="amber">BOOTSTRAP</Badge>
                                 : null}>
                            <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                                <p style={{ fontSize:T.xs, color:"var(--text-muted)", margin:0, lineHeight:1.55 }}>
                                    Derives TP/SL/lookahead from historical MFE/MAE. <strong>Run after first outcomes, then recompute outcomes.</strong> Each cycle improves measurement.
                                </p>
                                <Fld label="Timeframe to calibrate"
                                     hint={calibTf !== timeframe
                                        ? `⚠ Outcomes ran on ${timeframe} but calibrating ${calibTf} — they must match`
                                        : `✓ Matches outcomes timeframe (${timeframe})`}>
                                    <Sel value={calibTf} onChange={setCalibTf} options={TF_PRI.map(v => ({ value:v, label:v }))} />
                                </Fld>
                                <div className="ml-row-3">
                                    <Fld label="TP %ile" hint="p60 → ~60% hit">
                                        <Inp type="number" value={tpPct} onChange={v => setTpPct(Number(v))} />
                                    </Fld>
                                    <Fld label="SL %ile" hint="p25 → 75% survive">
                                        <Inp type="number" value={slPct} onChange={v => setSlPct(Number(v))} />
                                    </Fld>
                                    <Fld label="LA %ile" hint="p75 exit time">
                                        <Inp type="number" value={laPct} onChange={v => setLaPct(Number(v))} />
                                    </Fld>
                                </div>
                                <Fld label="Min samples per phase" hint="below this, PHASE_MODEL defaults used">
                                    <Inp type="number" value={minSamples} onChange={v => setMinSamples(Number(v))} />
                                </Fld>
                                <Btn onClick={handleCalibrate} loading={calibLoading} disabled={!symbol} variant="success">
                                    Calibrate from MFE/MAE data
                                </Btn>
                                {calibResult && (() => {
                                    if (calibResult.error) return <Alert type="error">{calibResult.error}</Alert>;
                                    if (calibResult.status === "NO_DATA") return <Alert type="warn">No outcome data yet — run Step 5 first as a bootstrap, then come back here.</Alert>;
                                    return (
                                        <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                                            <Alert type="success">
                                                <strong>{calibResult.phases_calibrated}</strong> phases calibrated · <strong>{calibResult.phases_skipped_insufficient_data}</strong> skipped (&lt;{minSamples} samples)
                                            </Alert>
                                            {calibResult.phases && (
                                                <div style={{ display:"flex", flexDirection:"column", gap:2, maxHeight:180, overflowY:"auto" }}>
                                                    {Object.entries(calibResult.phases)
                                                        .filter(([, v]) => v.status === "CALIBRATED")
                                                        .sort((a, b) => (b[1].gross_rr || 0) - (a[1].gross_rr || 0))
                                                        .map(([phase, info]) => (
                                                            <div key={phase} className="ml-ph-row">
                                                                <span style={{ fontWeight:500, fontSize:"0.68rem" }}>{phase}</span>
                                                                <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                                                                    <span style={{ fontSize:"0.67rem", color:"var(--accent-up)" }}>TP {info.optimal_tp}</span>
                                                                    <span style={{ fontSize:"0.67rem", color:"var(--accent-down)" }}>SL {info.optimal_sl}</span>
                                                                    <span style={{ fontSize:"0.67rem", color:"var(--text-muted)" }}>{info.optimal_la_min}m</span>
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
                        </Panel>

                        {/* 5 — Outcomes */}
                        <Panel title="Compute Strategy Outcomes"
                            badge={outcomeDone ? <Badge tone="up">{outcomeResult.rows_written?.toLocaleString()} rows</Badge> : null}>
                            <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                                <p style={{ fontSize:T.xs, color:"var(--text-muted)", margin:0, lineHeight:1.55 }}>
                                    Simulates every labelled bar using <strong>calibrated TP/SL/lookahead</strong>. Falls back to hardcoded defaults for uncalibrated phases. All history processed.
                                </p>
                                <Btn onClick={handleOutcomes} loading={outcomeLoading} disabled={!symbol}>Compute outcomes</Btn>
                                {outcomeResult && (() => {
                                    if (outcomeResult.error)    return <Alert type="error">{outcomeResult.error}</Alert>;
                                    if (outcomeResult._running) return <Alert type="info">{outcomeResult.message}</Alert>;
                                    return (
                                        <Alert type="success">
                                            {outcomeResult.rows_written?.toLocaleString()} rows · {outcomeResult.elapsed_sec}s
                                            {outcomeResult.phases_calibrated > 0
                                                ? <> · <strong>{outcomeResult.phases_calibrated}</strong> calibrated phases used</>
                                                : <span style={{ color:"#f59e0b" }}> · using defaults — calibrate first for better results</span>}
                                        </Alert>
                                    );
                                })()}
                            </div>
                        </Panel>

                    </div>

                    {/* ══════════════ RIGHT AREA ══════════════ */}
                    <div className="ml-right">

                        {/* 6 — Train Model */}
                        <Panel title="Train Model" badge={trainDone ? <Badge tone="up">run #{modelRunId}</Badge> : null}>
                            <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                                <div style={{ display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" }}>
                                    <Btn onClick={handleTrain} loading={trainLoading} disabled={!symbol}>
                                        Train {timeframe} model with HTF features
                                    </Btn>
                                    <Btn onClick={compareThresholds} loading={cmpLoading} disabled={!symbol || !modelRunId} variant="ghost" size="sm">
                                        Compare thresholds
                                    </Btn>
                                    <span style={{ fontSize:T.xs, color:"var(--text-muted)" }}>
                                        {timeframe} ← {mtf} ← {htf} · target = realized_r_net
                                    </span>
                                </div>

                                {trainResults?.error && <Alert type="error">{trainResults.error}</Alert>}

                                {trainResults && !trainResults.error && (
                                    <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                                        <div className="ml-row-3">
                                            <Stat label="Walk-fwd AUC" value={trainResults.wf_auc_mean?.toFixed(4)}
                                                tone={trainResults.wf_auc_mean > 0.57 ? "up" : trainResults.wf_auc_mean < 0.52 ? "down" : undefined}
                                                sub={trainResults.wf_auc_mean > 0.60 ? "✓ good signal" : trainResults.wf_auc_mean < 0.55 ? "⚠ weak" : "marginal"} />
                                            <Stat label="Walk-fwd MAE" value={trainResults.wf_mae_mean?.toFixed(4)} />
                                            <Stat label="Rows trained" value={trainResults.rows_trained?.toLocaleString()} />
                                        </div>

                                        {trainResults.wf_auc_mean !== undefined && trainResults.wf_auc_mean < 0.55 && (
                                            <Alert type="warn">
                                                AUC {trainResults.wf_auc_mean?.toFixed(3)} is below 0.55 — no reliable predictive power.
                                                Add more symbols across different market regimes before trusting live decisions.
                                            </Alert>
                                        )}

                                        {trainResults.phase_analysis && Object.keys(trainResults.phase_analysis).length > 0 && (
                                            <div>
                                                <div style={{ fontSize:T.xs, fontWeight:700, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:".06em", marginBottom:6 }}>
                                                    Phase analysis — sorted by expected R at threshold
                                                </div>
                                                <div style={{ display:"flex", flexDirection:"column", gap:2, maxHeight:250, overflowY:"auto" }}>
                                                    {Object.entries(trainResults.phase_analysis)
                                                        .sort((a, b) => (b[1].expected_r_at_threshold || 0) - (a[1].expected_r_at_threshold || 0))
                                                        .map(([phase, info]) => (
                                                            <div key={phase} className="ml-ph-row">
                                                                <span style={{ color:"var(--text-primary)", fontWeight:500 }}>{phase}</span>
                                                                <div style={{ display:"flex", gap:8, alignItems:"center" }}>
                                                                    <Badge tone={info.exec_class === "SKIP" ? "neutral" : "blue"}>{info.exec_class}</Badge>
                                                                    <span style={{ color:"var(--text-muted)", fontSize:"0.67rem" }}>n={info.samples}</span>
                                                                    <span style={{ fontWeight:700, color: info.avg_r > 0 ? "var(--accent-up)" : "var(--accent-down)" }}>
                                                                        {info.avg_r > 0 ? "+" : ""}{info.avg_r?.toFixed(3)}R
                                                                    </span>
                                                                    <span style={{ fontSize:"0.67rem", color:"var(--text-muted)" }}>th={info.recommended_threshold}</span>
                                                                </div>
                                                            </div>
                                                        ))}
                                                </div>
                                            </div>
                                        )}

                                        {cmpResult && (
                                            <Alert type="info">{cmpResult.instruction || "Threshold comparison completed. Run /run with each threshold to compare."}</Alert>
                                        )}
                                    </div>
                                )}
                            </div>
                        </Panel>

                        {/* Rule stats + Live Signal */}
                        <div className="ml-row-2">

                            {/* Rule performance */}
                            <Panel title="Rule Performance"
                                badge={<Btn size="sm" variant="ghost" onClick={fetchRuleStats} loading={ruleStatsLoading}>Refresh</Btn>}>
                                {!ruleStats ? (
                                    <p style={{ fontSize:T.xs, color:"var(--text-muted)", margin:0 }}>Select a symbol and click Refresh.</p>
                                ) : (
                                    <div style={{ display:"flex", flexDirection:"column", gap:0 }}>
                                        <div className="ml-ph-row">
                                            <span style={{ color:"var(--text-muted)" }}>{ruleStats.symbol} · {ruleStats.timeframe}</span>
                                            <Badge tone="neutral">{ruleStats.months_tested?.count || 0} months</Badge>
                                        </div>
                                        <div style={{ height:6 }} />
                                        {ruleStats.rules?.map(r => (
                                            <div key={r.name} className="ml-ph-row">
                                                <span style={{ fontWeight:700 }}>{r.name}</span>
                                                <div style={{ display:"flex", gap:10 }}>
                                                    <span style={{ color:"var(--accent-up)", fontVariantNumeric:"tabular-nums" }}>✓ {(r.success_rate * 100).toFixed(0)}%</span>
                                                    <span style={{ color:"var(--accent-down)", fontVariantNumeric:"tabular-nums" }}>✗ {(r.failure_rate * 100).toFixed(0)}%</span>
                                                    <span style={{ color:"var(--text-muted)" }}>n={r.samples}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </Panel>

                            {/* Live signal */}
                            <Panel title="Live Signal">
                                <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                                    <Fld label="LTF model run ID" hint="auto-filled after training">
                                        <Inp value={runIdLtf} onChange={setRunIdLtf} placeholder="auto-filled after training" />
                                    </Fld>
                                    <div style={{ display:"flex", gap:6 }}>
                                        <Btn size="sm" onClick={handlePredictSignal} loading={sigLoading} disabled={!symbol || !runIdLtf}>Single TF</Btn>
                                        <Btn size="sm" variant="secondary" onClick={handleHtfSignal} loading={htfSigLoading} disabled={!symbol || !runIdLtf}>HTF Pipeline</Btn>
                                    </div>

                                    {activeSig && (() => {
                                        if (activeSig.error) return <Alert type="error">{activeSig.error}</Alert>;
                                        if (activeSig.status === "NO_SIGNAL") return <Alert type="info">No signal — phase mapped to SKIP</Alert>;
                                        const prob = activeSig.combined_prob ?? activeSig.win_prob ?? 0;
                                        const dir  = activeSig.direction;
                                        const ec   = activeSig.ltf_exec_class ?? activeSig.exec_class;
                                        const dc   = dirColor(dir);
                                        return (
                                            <div className="ml-sig-box" style={{ borderColor:dc, background:`${dc}0d` }}>
                                                <div style={{ fontSize:"1.1rem", fontWeight:800, color:dc, letterSpacing:".04em", marginBottom:2 }}>{dir}</div>
                                                <div style={{ fontSize:T.xs, color:"var(--text-muted)", marginBottom:8 }}>{ec}</div>
                                                <div style={{ display:"flex", justifyContent:"center", gap:18 }}>
                                                    <div style={{ textAlign:"center" }}>
                                                        <div style={{ fontSize:"0.6rem", color:"var(--text-muted)" }}>WIN PROB</div>
                                                        <div style={{ fontSize:T.lg, fontWeight:700, color: prob > .6 ? "var(--accent-up)" : "var(--text-primary)", fontVariantNumeric:"tabular-nums" }}>{(prob*100).toFixed(1)}%</div>
                                                    </div>
                                                    <div style={{ textAlign:"center" }}>
                                                        <div style={{ fontSize:"0.6rem", color:"var(--text-muted)" }}>TP / SL</div>
                                                        <div style={{ fontSize:T.lg, fontWeight:700, fontVariantNumeric:"tabular-nums" }}>{activeSig.tp_atr}R / {activeSig.sl_atr}R</div>
                                                    </div>
                                                    {activeSig.size_multiplier !== undefined && (
                                                        <div style={{ textAlign:"center" }}>
                                                            <div style={{ fontSize:"0.6rem", color:"var(--text-muted)" }}>SIZE</div>
                                                            <div style={{ fontSize:T.lg, fontWeight:700, color: activeSig.size_multiplier < 1 ? "#f59e0b" : "var(--text-primary)" }}>{activeSig.size_multiplier}×</div>
                                                        </div>
                                                    )}
                                                </div>
                                                {activeSig.tf_aligned === false && <div style={{ marginTop:6, fontSize:T.xs, color:"#f59e0b" }}>⚠ TF misaligned — half size applied</div>}
                                                {!activeSig.recommended && <div style={{ marginTop:4, fontSize:T.xs, color:"var(--accent-down)" }}>Below threshold ({activeSig.threshold_used}) — not recommended</div>}
                                            </div>
                                        );
                                    })()}

                                    {htfSigResult?.stage_detail && Object.keys(htfSigResult.stage_detail).length > 0 && (
                                        <div>
                                            <div style={{ fontSize:T.xs, fontWeight:700, color:"var(--text-muted)", marginBottom:4 }}>STAGE PROBABILITIES</div>
                                            {Object.entries(htfSigResult.stage_detail).map(([stage, info]) => (
                                                <div key={stage} className="ml-ph-row">
                                                    <span style={{ fontWeight:700, textTransform:"uppercase", fontSize:"0.65rem" }}>{stage}</span>
                                                    <div style={{ display:"flex", gap:8 }}>
                                                        <span>{info.phase}</span>
                                                        <span style={{ fontWeight:700, color:"var(--accent-up)", fontVariantNumeric:"tabular-nums" }}>
                                                            {info.win_prob != null ? `${(info.win_prob*100).toFixed(1)}%` : "—"}
                                                        </span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {trainDone && (
                                        <div style={{ marginTop:4 }}>
                                            <div style={{ fontSize:T.xs, color:"var(--text-muted)", marginBottom:4 }}>MTF / HTF run IDs for 3-stage pipeline</div>
                                            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:6 }}>
                                                <Inp value={runIdMtf} onChange={setRunIdMtf} placeholder={`MTF (${mtf}) run ID`} />
                                                <Inp value={runIdHtf} onChange={setRunIdHtf} placeholder={`HTF (${htf}) run ID`} />
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </Panel>
                        </div>

                        {/* Equity curve */}
                        <Panel title="Equity Curve">
                            {equityLoading ? (
                                <div style={{ display:"flex", alignItems:"center", gap:8, color:"var(--text-muted)", fontSize:T.sm }}>
                                    <Spinner /> Loading equity curve…
                                </div>
                            ) : equityCurve.length < 2 ? (
                                <p style={{ fontSize:T.xs, color:"var(--text-muted)", margin:0 }}>Run paper trading to see the equity curve.</p>
                            ) : (() => {
                                const vals = equityCurve.map(p => p.capital ?? p.capital_after ?? 0);
                                const mn   = Math.min(...vals);
                                const mx   = Math.max(...vals);
                                const rng  = mx - mn || 1;
                                const W    = equityCurve.length - 1;
                                const pts  = vals.map((v, i) => `${i},${78 - ((v - mn) / rng) * 70}`).join(" ");
                                const up   = vals[vals.length - 1] >= vals[0];
                                const lc   = up ? "var(--accent-up)" : "var(--accent-down)";
                                return (
                                    <div>
                                        <div style={{ display:"flex", justifyContent:"space-between", marginBottom:8 }}>
                                            <span style={{ fontSize:T.xs, color:"var(--text-muted)" }}>{equityCurve.length} trades</span>
                                            <span style={{ fontSize:T.sm, fontWeight:700, color:lc, fontVariantNumeric:"tabular-nums" }}>
                                                {up ? "+" : ""}₹{(vals[vals.length-1] - vals[0]).toLocaleString(undefined, { maximumFractionDigits:0 })}
                                            </span>
                                        </div>
                                        <svg width="100%" height="80" viewBox={`0 0 ${W} 80`} preserveAspectRatio="none"
                                            style={{ display:"block", background:"var(--bg-tertiary)", borderRadius:6 }}>
                                            <polyline points={pts} fill="none" stroke={lc} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
                                        </svg>
                                    </div>
                                );
                            })()}
                        </Panel>

                        {/* 7 — Paper Trading */}
                        <Panel title="Paper Trading" badge={paperDone ? <Badge tone="up">COMPLETE</Badge> : null}>
                            <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                                <div className="ml-row-3">
                                    <Fld label="Starting capital (₹)">
                                        <Inp type="number" value={startCap} onChange={v => setStartCap(Number(v))} />
                                    </Fld>
                                    <Fld label="Margin / share (₹)">
                                        <Inp type="number" value={marginPS} onChange={v => setMarginPS(Number(v))} />
                                    </Fld>
                                    <Fld label="Min win prob" hint="per-phase thresholds applied">
                                        <Inp type="number" value={threshold} step="0.05" onChange={v => setThreshold(Number(v))} />
                                    </Fld>
                                </div>

                                <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                                    <Btn onClick={runPaperTrading} loading={paperLoading} disabled={!symbol || !modelRunId}>Run simulation</Btn>
                                    {paperLoading && (
                                        <>
                                            <div className="ml-prog-track">
                                                <div className="ml-prog-fill" style={{ width:`${paperPercent}%` }} />
                                            </div>
                                            <span style={{ fontSize:T.xs, color:"var(--text-muted)", whiteSpace:"nowrap" }}>{paperPercent}%</span>
                                        </>
                                    )}
                                </div>
                                {!paperLoading && paperProgress && paperResult && (
                                    <span style={{ fontSize:T.xs, color:"var(--text-muted)" }}>{paperProgress}</span>
                                )}

                                {paperResult?.error && <Alert type="error">{paperResult.error}</Alert>}

                                {paperResult && !paperResult.error && (
                                    <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                                        <div className="ml-row-3">
                                            <Stat label="Final capital" value={`₹${paperResult.final_capital?.toLocaleString()}`} tone={paperResult.net_pnl > 0 ? "up" : "down"} />
                                            <Stat label="Net P&L" value={`${paperResult.net_pnl > 0 ? "+" : ""}${paperResult.net_pnl_pct?.toFixed(2)}%`} tone={paperResult.net_pnl > 0 ? "up" : "down"} />
                                            <Stat label="Win rate" value={`${(paperResult.win_rate * 100).toFixed(1)}%`} tone={paperResult.win_rate > 0.50 ? "up" : undefined} />
                                            <Stat label="Expectancy" value={`${paperResult.expectancy_r > 0 ? "+" : ""}${paperResult.expectancy_r?.toFixed(3)}R`} tone={paperResult.expectancy_r > 0 ? "up" : "down"} />
                                            <Stat label="Max drawdown" value={`${paperResult.max_drawdown_pct?.toFixed(2)}%`} tone={paperResult.max_drawdown_pct > 20 ? "down" : undefined} />
                                            <Stat label="Total trades" value={paperResult.total_trades} />
                                        </div>

                                        {paperResult.expectancy_r !== undefined && paperResult.expectancy_r < 0 && (
                                            <Alert type="warn">
                                                Negative expectancy ({paperResult.expectancy_r?.toFixed(3)}R). Raise the threshold or add more training symbols.
                                            </Alert>
                                        )}

                                        {paperResult.per_phase_pnl && Object.keys(paperResult.per_phase_pnl).length > 0 && (
                                            <div>
                                                <div style={{ fontSize:T.xs, fontWeight:700, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:".06em", marginBottom:6 }}>P&L by phase</div>
                                                <div style={{ display:"flex", flexDirection:"column", gap:0 }}>
                                                    {Object.entries(paperResult.per_phase_pnl)
                                                        .sort((a, b) => b[1] - a[1])
                                                        .map(([phase, pnl]) => (
                                                            <div key={phase} className="ml-ph-row">
                                                                <span>{phase}</span>
                                                                <span style={{ fontWeight:700, fontVariantNumeric:"tabular-nums", color: pnl >= 0 ? "var(--accent-up)" : "var(--accent-down)" }}>
                                                                    {pnl >= 0 ? "+" : ""}₹{pnl.toLocaleString(undefined, { maximumFractionDigits:0 })}
                                                                </span>
                                                            </div>
                                                        ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </Panel>

                    </div>
                </div>
            </div>
        </div>
    );
}
