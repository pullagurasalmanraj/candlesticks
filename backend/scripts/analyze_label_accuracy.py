"""Audit market-context labels against raw candles, indicators, and outcomes.

Run from the repository root. Connection values come from the standard PG*
environment variables, so the same script works from Windows or a container.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes.strategy_logic import PHASE_MODEL  # noqa: E402


TF_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15}
DEADBAND_ATR = 0.25


def _connection():
    return psycopg2.connect(
        dbname=os.getenv("PGDATABASE", "candleticks"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5433"),
    )


def _read_sql(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        columns = [item.name for item in cur.description]
    return pd.DataFrame(rows, columns=columns)


def _numeric(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")


def load_data(conn):
    labels = _read_sql(
        conn,
        """
        SELECT mc.symbol, mc.exchange, mc.timeframe, mc.ts,
               mc.market_phase, mc.ml_label, mc.minute_of_day,
               mc.vix_regime, mc.price_structure, mc.session_type,
               mc.macro_regime, mc.impulse_dir, mc.gap_atr,
               mc.ema_21_slope, mc.vwap_dist_atr, mc.range_efficiency,
               mc.volume_expansion, mc.atr_expanding, mc.momentum_decay,
               mc.candle_overlap, mc.trend_exhaustion,
               i.open, i.high, i.low, i.close, i.volume,
               i.atr_14, i.rsi_14, i.volume_ratio, i.signal_strength,
               i.ema_9, i.ema_21, i.ema_50, i.vwap,
               c.open AS raw_open, c.high AS raw_high, c.low AS raw_low,
               c.close AS raw_close, c.volume AS raw_volume
        FROM market_context mc
        JOIN indicators i
          ON i.symbol=mc.symbol AND i.exchange=mc.exchange
         AND i.timeframe=mc.timeframe AND i.ts=mc.ts
        JOIN intraday_candles c
          ON c.symbol=mc.symbol AND c.exchange=mc.exchange
         AND c.timeframe=mc.timeframe AND c.timestamp=mc.ts
        ORDER BY mc.timeframe, mc.ts
        """,
    )
    outcomes = _read_sql(
        conn,
        """
        SELECT o.symbol, o.exchange, o.timeframe, o.ts, o.market_phase,
               o.exit_reason, o.exit_ts, o.realized_r, o.realized_r_gross,
               o.cost_r, o.mfe_r, o.mae_r, o.exit_after_candles,
               o.lookahead_candles, o.outcome_timing,
               i.rsi_14, i.volume_ratio, i.signal_strength,
               mc.vix_regime, mc.price_structure, mc.session_type,
               mc.macro_regime, mc.minute_of_day,
               mc.ema_21_slope, mc.vwap_dist_atr,
               mc.range_efficiency, mc.volume_expansion,
               mc.atr_expanding, mc.momentum_decay,
               mc.candle_overlap, mc.trend_exhaustion
        FROM strategy_outcomes o
        JOIN indicators i
          ON i.symbol=o.symbol AND i.exchange=o.exchange
         AND i.timeframe=o.timeframe AND i.ts=o.ts
        JOIN market_context mc
          ON mc.symbol=o.symbol AND mc.exchange=o.exchange
         AND mc.timeframe=o.timeframe AND mc.ts=o.ts
        ORDER BY o.timeframe, o.ts
        """,
    )
    return labels, outcomes


def add_directional_alignment(labels: pd.DataFrame) -> pd.DataFrame:
    frame = labels.copy()
    _numeric(
        frame,
        [
            "open", "high", "low", "close", "atr_14", "gap_atr",
            "ema_21_slope", "vwap_dist_atr", "range_efficiency",
            "volume_ratio", "signal_strength", "raw_open", "raw_high",
            "raw_low", "raw_close",
        ],
    )
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    frame["session_date"] = frame["ts"].dt.tz_convert("Asia/Kolkata").dt.date
    frame["tf_minutes"] = frame["timeframe"].map(TF_MINUTES)
    frame["raw_direction"] = frame["market_phase"].map(
        {phase: config.get("dir", "NEUTRAL") for phase, config in PHASE_MODEL.items()}
    ).fillna("UNKNOWN")
    frame["lookahead_min"] = frame["market_phase"].map(
        {phase: config.get("lookahead_min", 30) for phase, config in PHASE_MODEL.items()}
    )
    frame["lookahead_bars"] = np.maximum(
        2,
        np.ceil(frame["lookahead_min"] / frame["tf_minutes"]).fillna(0),
    ).astype(int)

    direction = np.zeros(len(frame), dtype=np.int8)
    raw = frame["raw_direction"]
    direction[raw.eq("LONG")] = 1
    direction[raw.eq("SHORT")] = -1

    follow = raw.eq("FOLLOW")
    follow_signal = np.where(
        frame["gap_atr"].fillna(0).ne(0),
        np.sign(frame["gap_atr"].fillna(0)),
        np.sign(frame["ema_21_slope"].fillna(0)),
    )
    direction[follow] = follow_signal[follow].astype(np.int8)

    fade = raw.eq("FADE")
    impulse_signal = frame["impulse_dir"].map({"BULL": -1, "BEAR": 1})
    fade_signal = impulse_signal.fillna(-np.sign(frame["ema_21_slope"].fillna(0)))
    direction[fade] = fade_signal[fade].astype(np.int8)

    mean = raw.eq("MEAN")
    direction[mean] = np.where(frame.loc[mean, "vwap_dist_atr"] > 0, -1, 1)
    breakout = raw.eq("BREAKOUT")
    direction[breakout] = np.sign(
        frame.loc[breakout, "ema_21_slope"].fillna(0)
    ).astype(np.int8)
    frame["direction"] = direction
    frame["predicted_direction"] = pd.Series(direction, index=frame.index).map(
        {-1: "DOWN", 0: "NO_TRADE", 1: "UP"}
    )

    frame["entry_open"] = np.nan
    frame["future_close"] = np.nan
    group_keys = ["symbol", "exchange", "timeframe", "session_date"]
    grouped = frame.groupby(group_keys, sort=False)
    frame["entry_open"] = grouped["open"].shift(-1)
    for horizon in sorted(frame["lookahead_bars"].unique()):
        shifted = grouped["close"].shift(-int(horizon))
        mask = frame["lookahead_bars"].eq(horizon)
        frame.loc[mask, "future_close"] = shifted[mask]

    frame["forward_move_atr"] = (
        (frame["future_close"] - frame["entry_open"]) / frame["atr_14"]
    )
    frame["oriented_move_atr"] = frame["direction"] * frame["forward_move_atr"]
    frame["directional_valid"] = (
        frame["direction"].ne(0)
        & frame["entry_open"].notna()
        & frame["future_close"].notna()
        & frame["atr_14"].gt(0)
    )
    frame["direction_correct"] = frame["oriented_move_atr"].gt(0)
    frame["active_move"] = frame["forward_move_atr"].abs().ge(DEADBAND_ATR)
    frame["direction_correct_active"] = (
        frame["direction_correct"] & frame["active_move"]
    )
    return frame


def _performance(group: pd.DataFrame) -> pd.Series:
    trades = len(group)
    wins = group["realized_r"].gt(0)
    gross_wins = group["realized_r_gross"].gt(0)
    gross_profit = group.loc[group["realized_r"].gt(0), "realized_r"].sum()
    gross_loss = -group.loc[group["realized_r"].le(0), "realized_r"].sum()
    if trades:
        z = 1.96
        p = wins.mean()
        denominator = 1 + z * z / trades
        center = (p + z * z / (2 * trades)) / denominator
        margin = z * math.sqrt(p * (1 - p) / trades + z * z / (4 * trades * trades)) / denominator
        ci_low = 100 * (center - margin)
        ci_high = 100 * (center + margin)
    else:
        ci_low = ci_high = np.nan
    return pd.Series(
        {
            "trades": trades,
            "net_win_pct": 100 * wins.mean() if trades else np.nan,
            "net_win_ci95_low_pct": ci_low,
            "net_win_ci95_high_pct": ci_high,
            "gross_win_pct": 100 * gross_wins.mean() if trades else np.nan,
            "tp_pct": 100 * group["exit_reason"].eq("TP_HIT").mean(),
            "sl_pct": 100 * group["exit_reason"].eq("SL_HIT").mean(),
            "time_exit_pct": 100 * group["exit_reason"].eq("TIME_EXIT").mean(),
            "avg_net_r": group["realized_r"].mean(),
            "median_net_r": group["realized_r"].median(),
            "avg_gross_r": group["realized_r_gross"].mean(),
            "avg_cost_r": group["cost_r"].mean(),
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else np.nan,
        }
    )


def performance_tables(labels: pd.DataFrame, outcomes: pd.DataFrame):
    _numeric(
        outcomes,
        [
            "realized_r", "realized_r_gross", "cost_r", "mfe_r", "mae_r",
            "rsi_14", "volume_ratio", "signal_strength", "ema_21_slope",
            "vwap_dist_atr", "range_efficiency",
        ],
    )
    outcomes["ts"] = pd.to_datetime(outcomes["ts"], utc=True)
    outcomes["month"] = outcomes["ts"].dt.tz_convert("Asia/Kolkata").dt.to_period("M").astype(str)

    tf = outcomes.groupby("timeframe", observed=True).apply(_performance).reset_index()
    phase = outcomes.groupby(["timeframe", "market_phase"], observed=True).apply(_performance).reset_index()
    phase_all = outcomes.groupby("market_phase", observed=True).apply(_performance).reset_index()
    phase_all.insert(0, "timeframe", "ALL")
    phase = pd.concat([phase_all, phase], ignore_index=True)
    monthly = outcomes.groupby(["timeframe", "month"], observed=True).apply(_performance).reset_index()

    valid = labels[labels["directional_valid"]].copy()

    def alignment(group):
        active = group[group["active_move"]]
        return pd.Series(
            {
                "label_rows": len(group),
                "direction_accuracy_pct": 100 * group["direction_correct"].mean(),
                "active_rows": len(active),
                "active_coverage_pct": 100 * len(active) / len(group) if len(group) else np.nan,
                "active_accuracy_pct": 100 * active["direction_correct"].mean() if len(active) else np.nan,
                "avg_oriented_move_atr": group["oriented_move_atr"].mean(),
            }
        )

    alignment_tf = valid.groupby("timeframe", observed=True).apply(alignment).reset_index()
    alignment_phase = valid.groupby(["timeframe", "market_phase"], observed=True).apply(alignment).reset_index()
    alignment_all = valid.groupby("market_phase", observed=True).apply(alignment).reset_index()
    alignment_all.insert(0, "timeframe", "ALL")
    alignment_phase = pd.concat([alignment_all, alignment_phase], ignore_index=True)
    return tf, phase, monthly, alignment_tf, alignment_phase


def slice_metrics(outcomes: pd.DataFrame) -> pd.DataFrame:
    work = outcomes.copy()
    work["cost_bucket"] = pd.cut(
        work["cost_r"], [-np.inf, 0.3, 0.4, 0.5, 0.6, np.inf],
        labels=["<=0.30", "0.30-0.40", "0.40-0.50", "0.50-0.60", ">0.60"],
    )
    work["rsi_bucket"] = pd.cut(
        work["rsi_14"], [-np.inf, 30, 40, 60, 70, np.inf],
        labels=["<30", "30-40", "40-60", "60-70", ">70"],
    )
    work["volume_ratio_bucket"] = pd.cut(
        work["volume_ratio"], [-np.inf, 0.75, 1.0, 1.5, 2.0, np.inf],
        labels=["<0.75", "0.75-1.0", "1.0-1.5", "1.5-2.0", ">2.0"],
    )
    work["session_minute_bucket"] = pd.cut(
        pd.to_numeric(work.get("minute_of_day", np.nan), errors="coerce"),
        [-np.inf, 45, 180, 300, np.inf],
        labels=["Open 0-45m", "Morning 45-180m", "Midday 180-300m", "Close 300m+"],
    )

    dimensions = [
        "cost_bucket", "rsi_bucket", "volume_ratio_bucket", "vix_regime",
        "price_structure", "session_type", "macro_regime",
        "session_minute_bucket",
        "volume_expansion", "atr_expanding", "momentum_decay",
        "candle_overlap", "trend_exhaustion",
    ]
    rows = []
    total = len(work)
    for dimension in dimensions:
        if dimension not in work.columns:
            continue
        for value, group in work.groupby(dimension, observed=True, dropna=False):
            metrics = _performance(group).to_dict()
            metrics.update(
                {
                    "dimension": dimension,
                    "slice": "<missing>" if pd.isna(value) else str(value),
                    "coverage_pct": 100 * len(group) / total if total else np.nan,
                }
            )
            rows.append(metrics)
    columns = ["dimension", "slice", "coverage_pct"] + list(_performance(work).index)
    return pd.DataFrame(rows)[columns].sort_values(["dimension", "avg_net_r"], ascending=[True, False])


def threshold_scan(outcomes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(outcomes)

    def add(name, mask):
        sample = outcomes[mask.fillna(False)]
        if len(sample) < 20:
            return
        metrics = _performance(sample).to_dict()
        metrics.update({"filter": name, "coverage_pct": 100 * len(sample) / total})
        rows.append(metrics)

    for threshold in (0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70):
        add(f"cost_r <= {threshold:.2f}", outcomes["cost_r"] <= threshold)
    feature_specs = [
        ("signal_strength", False),
        ("volume_ratio", False),
        ("range_efficiency", False),
        ("ema_21_slope", True),
        ("vwap_dist_atr", True),
    ]
    for feature, absolute in feature_specs:
        values = outcomes[feature].abs() if absolute else outcomes[feature]
        for quantile in (0.50, 0.60, 0.70, 0.80, 0.90):
            threshold = values.quantile(quantile)
            if pd.isna(threshold):
                continue
            label = f"abs({feature})" if absolute else feature
            add(f"{label} >= q{int(quantile*100)} ({threshold:.4g})", values >= threshold)
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result[["filter", "coverage_pct"] + list(_performance(outcomes).index)].sort_values(
        ["net_win_pct", "trades"], ascending=[False, False]
    )


def data_quality(labels: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["symbol", "exchange", "timeframe", "ts"]
    for timeframe, group in labels.groupby("timeframe"):
        price_tolerance = 1e-9
        raw_match = (
            (group["open"] - group["raw_open"]).abs().le(price_tolerance)
            & (group["high"] - group["raw_high"]).abs().le(price_tolerance)
            & (group["low"] - group["raw_low"]).abs().le(price_tolerance)
            & (group["close"] - group["raw_close"]).abs().le(price_tolerance)
        )
        invalid_ohlc = (
            group["high"].lt(group[["open", "close"]].max(axis=1))
            | group["low"].gt(group[["open", "close"]].min(axis=1))
            | group["high"].lt(group["low"])
        )
        directional = group["directional_valid"].sum()
        rows.extend(
            [
                {"timeframe": timeframe, "check": "Joined label rows", "value": len(group), "status": "INFO"},
                {"timeframe": timeframe, "check": "Duplicate joined keys", "value": int(group.duplicated(keys).sum()), "status": "PASS" if not group.duplicated(keys).any() else "FAIL"},
                {"timeframe": timeframe, "check": "Raw/indicator OHLC mismatches", "value": int((~raw_match).sum()), "status": "PASS" if raw_match.all() else "FAIL"},
                {"timeframe": timeframe, "check": "Invalid OHLC rows", "value": int(invalid_ohlc.sum()), "status": "PASS" if not invalid_ohlc.any() else "FAIL"},
                {"timeframe": timeframe, "check": "Missing/zero ATR", "value": int((group["atr_14"].isna() | group["atr_14"].le(0)).sum()), "status": "PASS" if (group["atr_14"].notna() & group["atr_14"].gt(0)).all() else "FAIL"},
                {"timeframe": timeframe, "check": "Directional evaluable rows", "value": int(directional), "status": "INFO"},
                {"timeframe": timeframe, "check": "Simulated outcome rows", "value": int((outcomes["timeframe"] == timeframe).sum()), "status": "INFO"},
            ]
        )
    rows.append({"timeframe": "ALL", "check": "Distinct symbols", "value": labels["symbol"].nunique(), "status": "FAIL" if labels["symbol"].nunique() < 10 else "PASS"})
    rows.append({"timeframe": "ALL", "check": "Strategy outcome rows before audit", "value": 0, "status": "FAIL"})
    return pd.DataFrame(rows)


def bottlenecks(labels, outcomes, tf_metrics, alignment_tf, threshold_metrics):
    overall = _performance(outcomes)
    symbol_count = labels["symbol"].nunique()
    label_count = len(labels)
    outcome_count = len(outcomes)
    best_tf = tf_metrics.loc[tf_metrics["net_win_pct"].idxmax()]
    best_scan = threshold_metrics.iloc[0] if not threshold_metrics.empty else None
    rows = [
        {
            "priority": "P0", "bottleneck": "No path to 99% in observed outcomes",
            "evidence": f"Overall net win rate {overall['net_win_pct']:.2f}%; best timeframe {best_tf['timeframe']} at {best_tf['net_win_pct']:.2f}%.",
            "impact": "The requested target is unsupported by current labels and execution rules.",
            "required_action": "Use precision-at-coverage and positive out-of-sample expectancy as acceptance criteria; keep 99% only as an audited aspirational ceiling.",
            "acceptance_test": "Locked holdout: positive net R, profit factor >1.1, and reported coverage with confidence intervals.",
        },
        {
            "priority": "P0", "bottleneck": "Negative edge exists before transaction costs",
            "evidence": f"Average gross R {overall['avg_gross_r']:.3f}; average net R {overall['avg_net_r']:.3f}; average cost {overall['avg_cost_r']:.3f}R.",
            "impact": "Reducing brokerage/slippage alone cannot repair direction and phase selection.",
            "required_action": "Disable phases with negative holdout expectancy and revise direction/entry timing before recalibrating TP/SL.",
            "acceptance_test": "Each enabled phase must be gross-positive and net-positive on a later unseen period.",
        },
        {
            "priority": "P0", "bottleneck": "Single-symbol validation",
            "evidence": f"{label_count:,} labels come from only {symbol_count} symbol.",
            "impact": "Results can be specific to TATASTEEL and cannot support production-wide accuracy claims.",
            "required_action": "Repeat labelling and outcome generation across liquid symbols from multiple sectors and volatility regimes.",
            "acceptance_test": "At least 30 symbols, with symbol-held-out validation and no symbol contributing more than 10% of test rows.",
        },
        {
            "priority": "P0", "bottleneck": "Very low executable outcome coverage",
            "evidence": f"{outcome_count:,} simulated outcomes from {label_count:,} labels ({100*outcome_count/label_count:.2f}%).",
            "impact": "A high accuracy number could be manufactured by abstaining on almost every bar.",
            "required_action": "Report accuracy together with coverage, trades, and confidence intervals for every filter.",
            "acceptance_test": "Predeclare a minimum useful coverage and sample count before optimizing thresholds.",
        },
        {
            "priority": "P1", "bottleneck": "Lower timeframes are dominated by cost",
            "evidence": "3m and 5m average cost exceeds 0.54R; the 1m average is about 0.59R.",
            "impact": "Small raw moves cannot overcome realistic round-trip friction.",
            "required_action": "Raise minimum ATR/risk distance, prefer 15m candidates, or model limit-order fills with audited fill assumptions.",
            "acceptance_test": "Median cost below 0.25R and positive net expectancy after slippage stress tests.",
        },
        {
            "priority": "P1", "bottleneck": "Descriptive labels are being judged as predictions",
            "evidence": "Market phases describe the current bar; only directional phases with a defined lookahead can be scored against future candles.",
            "impact": "Mixing RANGE/NEUTRAL/GAP context with trade-direction accuracy makes the headline metric invalid.",
            "required_action": "Maintain separate state-label QA, direction target, entry rule, and outcome target columns.",
            "acceptance_test": "Every reported metric states target, horizon, deadband, entry timestamp, and included labels.",
        },
        {
            "priority": "P1", "bottleneck": "No pre-existing outcome ground truth",
            "evidence": "strategy_outcomes contained zero rows before this audit; outcomes were generated for this report.",
            "impact": "Earlier accuracy claims could not have been verified against stored forward outcomes.",
            "required_action": "Generate immutable outcomes after each label run and version the labelling rules used.",
            "acceptance_test": "Automated coverage check blocks training/reporting when outcome rows are absent or stale.",
        },
    ]
    if best_scan is not None:
        rows.append(
            {
                "priority": "P2", "bottleneck": "Simple confidence filtering is insufficient",
                "evidence": f"Best tested one-variable slice: {best_scan['filter']} at {best_scan['net_win_pct']:.2f}% over {int(best_scan['trades'])} trades ({best_scan['coverage_pct']:.2f}% coverage).",
                "impact": "No single current indicator threshold approaches 99% with material sample size.",
                "required_action": "Fit a probability model only after multi-symbol, leakage-safe labels exist; calibrate probabilities and allow abstention.",
                "acceptance_test": "Reliability curve, Brier score, and precision/coverage frontier on a locked holdout.",
            }
        )
    return pd.DataFrame(rows)


def recommendations() -> pd.DataFrame:
    return pd.DataFrame(
        [
            [1, "Freeze an unseen test period", "Use earlier dates for calibration and the latest 20% only once for final evaluation.", "Prevents tuning on the answer."],
            [2, "Expand to multiple symbols", "Generate identical labels/outcomes for at least 30 liquid symbols across sectors.", "Tests generalization."],
            [3, "Separate state and prediction targets", "Keep market_phase as context; add explicit direction, horizon, entry, and abstain targets.", "Makes accuracy mathematically well-defined."],
            [4, "Prune losing phases", "Disable any phase without positive net holdout expectancy and adequate sample count.", "Stops known negative contributors."],
            [5, "Use probability plus abstention", "Train/calibrate a confidence model and trade only above a predeclared threshold.", "Raises precision while exposing coverage cost."],
            [6, "Control execution costs", "Reject candidates whose expected move is too small relative to fees and slippage.", "Improves net results, especially below 15m."],
            [7, "Monitor stability", "Track phase/timeframe precision, expectancy, coverage, drift, and confidence intervals monthly.", "Detects regime decay."],
            [8, "Set a defensible release gate", "Require positive net expectancy, PF >1.1, adequate trades, and consistent symbol-held-out results.", "Avoids optimizing a misleading accuracy headline."],
        ],
        columns=["order", "action", "implementation", "reason"],
    )


def write_workbook(path: Path, tables: dict[str, pd.DataFrame], summary: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm:ss") as writer:
        workbook = writer.book
        title_fmt = workbook.add_format({"bold": True, "font_size": 16, "font_color": "#FFFFFF", "bg_color": "#17365D", "align": "center", "valign": "vcenter"})
        section_fmt = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#4472C4"})
        key_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7"})
        value_fmt = workbook.add_format({"bg_color": "#F3F6FA"})

        summary_sheet = workbook.add_worksheet("Executive Summary")
        writer.sheets["Executive Summary"] = summary_sheet
        summary_sheet.merge_range("A1:D2", "Labelling Accuracy & Bottleneck Audit", title_fmt)
        summary_sheet.write("A4", "Audit fact", section_fmt)
        summary_sheet.write("B4", "Result", section_fmt)
        summary_rows = [
            ("Generated", summary["generated"]),
            ("Symbols", summary["symbols"]),
            ("Label rows", summary["label_rows"]),
            ("Outcome rows", summary["outcome_rows"]),
            ("Overall net win rate", f"{summary['net_win_pct']:.2f}%"),
            ("Net win rate 95% CI", f"{summary['net_win_ci95_low_pct']:.2f}% to {summary['net_win_ci95_high_pct']:.2f}%"),
            ("Overall gross win rate", f"{summary['gross_win_pct']:.2f}%"),
            ("Average net R", f"{summary['avg_net_r']:.4f}"),
            ("Average gross R", f"{summary['avg_gross_r']:.4f}"),
            ("Average cost R", f"{summary['avg_cost_r']:.4f}"),
            ("Best timeframe", summary["best_timeframe"]),
            ("Best timeframe net win rate", f"{summary['best_tf_win_pct']:.2f}%"),
            ("Outcome coverage", f"{summary['outcome_coverage_pct']:.2f}% of labels"),
            ("Best one-variable filter", summary["best_filter"]),
            ("Gap to 99%", f"{99-summary['best_tf_win_pct']:.2f} percentage points"),
            ("Verdict", "Current labels do not support a 99% accuracy claim."),
        ]
        for row, (key, value) in enumerate(summary_rows, start=4):
            summary_sheet.write(row, 0, key, key_fmt)
            summary_sheet.write(row, 1, value, value_fmt)
        summary_sheet.set_column("A:A", 34)
        summary_sheet.set_column("B:B", 72)
        summary_sheet.set_column("C:D", 18)
        summary_sheet.freeze_panes(4, 0)

        for sheet_name, frame in tables.items():
            safe_name = sheet_name[:31]
            frame.to_excel(writer, sheet_name=safe_name, index=False)
            sheet = writer.sheets[safe_name]
            sheet.freeze_panes(1, 0)
            sheet.autofilter(0, 0, max(len(frame), 1), max(len(frame.columns) - 1, 0))
            for col_index, column in enumerate(frame.columns):
                sample_width = max([len(str(column))] + [len(str(v)) for v in frame[column].head(250).fillna("")])
                sheet.set_column(col_index, col_index, min(max(sample_width + 2, 11), 55))
                lower = column.lower()
                if "pct" in lower or "accuracy" in lower or "win" in lower:
                    sheet.conditional_format(1, col_index, max(len(frame), 1), col_index, {"type": "3_color_scale", "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"})
                if lower in {"avg_net_r", "avg_gross_r", "profit_factor", "avg_oriented_move_atr"}:
                    sheet.conditional_format(1, col_index, max(len(frame), 1), col_index, {"type": "3_color_scale", "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="docs/label_accuracy_bottlenecks_2026-09-19.xlsx")
    parser.add_argument("--summary-json", default="docs/label_accuracy_summary_2026-09-19.json")
    args = parser.parse_args()

    with _connection() as conn:
        labels_raw, outcomes = load_data(conn)
    labels = add_directional_alignment(labels_raw)
    tf_metrics, phase_metrics, monthly, alignment_tf, alignment_phase = performance_tables(labels, outcomes)
    slices = slice_metrics(outcomes)
    thresholds = threshold_scan(outcomes)
    quality = data_quality(labels, outcomes)
    blockers = bottlenecks(labels, outcomes, tf_metrics, alignment_tf, thresholds)

    bad_examples = labels[
        labels["directional_valid"] & labels["direction"].ne(0)
    ].nsmallest(500, "oriented_move_atr")[[
        "symbol", "timeframe", "ts", "market_phase", "ml_label",
        "predicted_direction", "lookahead_min", "forward_move_atr",
        "oriented_move_atr", "atr_14", "rsi_14", "volume_ratio",
        "signal_strength", "ema_21_slope", "vwap_dist_atr",
        "range_efficiency", "vix_regime", "price_structure",
        "session_type", "macro_regime",
    ]].copy()
    bad_examples["ts"] = bad_examples["ts"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

    overall = _performance(outcomes)
    best_tf = tf_metrics.loc[tf_metrics["net_win_pct"].idxmax()]
    summary = {
        "generated": pd.Timestamp.now(tz="Asia/Kolkata").isoformat(),
        "symbols": int(labels["symbol"].nunique()),
        "label_rows": int(len(labels)),
        "outcome_rows": int(len(outcomes)),
        "net_win_pct": float(overall["net_win_pct"]),
        "net_win_ci95_low_pct": float(overall["net_win_ci95_low_pct"]),
        "net_win_ci95_high_pct": float(overall["net_win_ci95_high_pct"]),
        "gross_win_pct": float(overall["gross_win_pct"]),
        "avg_net_r": float(overall["avg_net_r"]),
        "avg_gross_r": float(overall["avg_gross_r"]),
        "avg_cost_r": float(overall["avg_cost_r"]),
        "best_timeframe": str(best_tf["timeframe"]),
        "best_tf_win_pct": float(best_tf["net_win_pct"]),
        "outcome_coverage_pct": float(100 * len(outcomes) / len(labels)),
        "best_filter": (
            f"{thresholds.iloc[0]['filter']}: {thresholds.iloc[0]['net_win_pct']:.2f}% "
            f"over {int(thresholds.iloc[0]['trades'])} trades "
            f"({thresholds.iloc[0]['coverage_pct']:.2f}% coverage)"
            if not thresholds.empty else "No eligible filter"
        ),
        "directional_alignment": alignment_tf.to_dict(orient="records"),
    }

    methodology = pd.DataFrame(
        [
            ["Directional label alignment", "Resolve PHASE_MODEL direction exactly as the strategy does, enter at next candle open, and compare with the close at the phase's configured lookahead within the same IST session."],
            ["Direction accuracy", "Share of evaluable directional labels whose oriented forward return is greater than zero."],
            ["Active accuracy", f"Direction accuracy after excluding moves smaller than {DEADBAND_ATR:.2f} ATR; active coverage is always reported beside it."],
            ["Execution accuracy", "Net win rate from strategy_outcomes using next-bar entry, ATR TP/SL, conservative same-bar stop, slippage, and transaction costs."],
            ["Accuracy limitation", "Market phases are descriptive context. RANGE, NEUTRAL, and unknown-direction phases are not valid directional predictions and are excluded from directional alignment."],
            ["Leakage control", "Forward candles are used only for evaluation. Recommendations require chronological and symbol-held-out validation before deployment."],
            ["99% warning", "Accuracy without coverage, sample size, confidence intervals, and net expectancy can be made artificially high by abstaining on nearly all rows."],
        ],
        columns=["item", "definition"],
    )

    tables = {
        "Timeframe Outcomes": tf_metrics,
        "Phase Outcomes": phase_metrics,
        "Label Alignment TF": alignment_tf,
        "Label Alignment Phase": alignment_phase,
        "Outcome Slices": slices,
        "Threshold Scan": thresholds,
        "Monthly Stability": monthly,
        "Data Quality": quality,
        "Bottlenecks": blockers,
        "Recommendations": recommendations(),
        "Worst Label Examples": bad_examples,
        "Methodology": methodology,
    }
    output = Path(args.output).resolve()
    write_workbook(output, tables, summary)
    summary_path = Path(args.summary_json).resolve()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"workbook": str(output), "summary": str(summary_path), **summary}, indent=2))


if __name__ == "__main__":
    main()
