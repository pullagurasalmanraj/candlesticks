"""Exploratory, read-only directional audit; no barriers, fees, writers or routes."""
from collections import Counter, defaultdict
import math
import re

import numpy as np
import pandas as pd

from db import get_db_conn, read_sql_safe
from routes.strategy import STORY_INPUT_COLUMNS
from routes.strategy_comparison import (
    SYMBOLS, _COMPARISON_JOIN, _database_read_diagnostics,
    _dataframe_story_counts, _label_loss_stages, _prepare_frame,
)
from routes.strategy_dates import _research_date_window, _research_window_metadata
from routes.strategy_logic import (
    PHASE_MODEL, STORY_TRADE_DEFAULTS, _legacy_trade_direction,
    _resolve_story_trade, _story_trade_context,
)

AUDIT_VERSION = "STORY_DIRECTIONAL_EDGE_EXPLORATORY_V1"
HORIZONS = (1, 3, 6, 9)
ANCHOR_WINDOW = {"from_date": "2000-01-01", "to_date": "2026-10-18",
                 "holdout_from_date": "2026-07-14"}
EXPECTED_COUNTS = {"ITC": 3011, "TATASTEEL": 3072}
MIN_CI_DAYS = 20
MAX_CONTROL_DAYS = 60
MAX_CONTROLS = 3
VOLATILITY_RATIO = 1.25
DIMENSIONS = ("story_regime", "bar_event", "direction", "setup_key")


def _positive(value):
    return math.isfinite(value) and value > 0


def _classify(interval):
    if interval is None:
        return "STATISTICALLY_INCONCLUSIVE"
    if interval[0] > 0:
        return "POSITIVE"
    if interval[1] < 0:
        return "NEGATIVE"
    return "STATISTICALLY_INCONCLUSIVE"


def _cluster_interval(mean, scores, n):
    """CR1 day-score variance; asymptotic normal, not iid candle errors."""
    days = len(scores)
    if days < MIN_CI_DAYS or not n:
        return None
    se = math.sqrt(days / (days - 1) * sum(v*v for v in scores.values())) / n
    return [float(mean - 1.96*se), float(mean + 1.96*se)]


def _distribution(values):
    if not values:
        return {"mean": None, "median": None, "p10": None, "p90": None}
    a = np.asarray(values, dtype=float)
    return {"mean": float(np.mean(a)), "median": float(np.median(a)),
            "p10": float(np.quantile(a, .1)), "p90": float(np.quantile(a, .9))}


def _estimate(values, days):
    if not values:
        return {**_distribution([]), "ci95_day_clustered": None}
    mean = float(np.mean(values))
    scores = defaultdict(float)
    for v, day in zip(values, days):
        scores[day] += v - mean
    return {**_distribution(values), "ci95_day_clustered": _cluster_interval(mean, scores, len(values))}


def _cohort(frame):
    """Call the existing resolver unchanged, including legacy GAP direction."""
    signals, eligible, reasons = [], set(), Counter()
    for i, row in enumerate(frame.to_dict("records")):
        story = _story_trade_context({k: row.get(k) for k in STORY_INPUT_COLUMNS})
        cfg = PHASE_MODEL.get(row.get("market_phase"))
        gap_direction = None
        if story["story_regime"] == "GAP_AUCTION" and cfg:
            gap_direction = _legacy_trade_direction(
                cfg["dir"], row.get("gap_atr"), row.get("ema_21_slope"),
                row.get("impulse_dir"), row.get("vwap_dist_pct"))
        decision = _resolve_story_trade(story, gap_direction=gap_direction)
        reasons[decision["eligibility_reason"]] += 1
        if decision["eligible"]:
            eligible.add(i)
            signals.append({"index": i, "direction": decision["trade_direction"],
                            "setup_key": decision["setup_key"],
                            "story_regime": story["story_regime"], "bar_event": story["bar_event"]})
    return signals, eligible, dict(reasons)


class _History:
    def __init__(self, frame, split_at):
        self.frame = _prepare_frame(frame)
        self.ts = self.frame.ts.tolist()
        local = self.frame.ts.dt.tz_convert("Asia/Kolkata")
        self.days = local.dt.date.to_numpy()
        self.day_ids = {d: j for j, d in enumerate(sorted(set(self.days)))}
        self.slots = (local.dt.hour*60 + local.dt.minute).to_numpy()
        self.periods = np.where(self.frame.ts < split_at, "research", "holdout")
        self.prices = {k: pd.to_numeric(self.frame[k], errors="coerce").to_numpy(dtype=float)
                       for k in ("open", "high", "low", "close", "atr_14")}
        self.ends = np.empty(len(self.frame), dtype=int)
        end = len(self.frame)-1
        for i in range(len(self.frame)-1, -1, -1):
            if i == len(self.frame)-1 or self.days[i] != self.days[i+1]:
                end = i
            self.ends[i] = end

    def outcome(self, i, direction, horizon):
        """H=1 is next-open to next-close; H bars include the entry candle."""
        entry, exit_ = i+1, i+horizon
        atr = self.prices["atr_14"][i]
        if not _positive(atr):
            return None, "INVALID_SIGNAL_ATR"
        if entry > self.ends[i]:
            return None, "NO_SAME_SESSION_ENTRY"
        if exit_ > self.ends[i]:
            return None, "INSUFFICIENT_SAME_SESSION_HORIZON"
        # Do not silently turn 3 five-minute bars into a longer elapsed horizon.
        if any(self.ts[j]-self.ts[j-1] != pd.Timedelta(minutes=5) for j in range(entry, exit_+1)):
            return None, "MISSING_5M_INTERVAL"
        p = self.prices
        reference = p["open"][entry]
        high, low, close = (p[k][entry:exit_+1] for k in ("high", "low", "close"))
        opens = p["open"][entry:exit_+1]
        if (not _positive(reference) or not all(np.isfinite(a).all() and (a > 0).all()
                                               for a in (opens, high, low, close)) or
                (high < np.maximum(opens, close)).any() or (low > np.minimum(opens, close)).any()):
            return None, "INVALID_FUTURE_OHLC"
        sign = 1 if direction == "LONG" else -1
        points = sign*(close[-1]-reference)
        favorable = high-reference if sign == 1 else reference-low
        adverse = low-reference if sign == 1 else reference-high
        mfe, mae = max(0., float(np.max(favorable))), min(0., float(np.min(adverse)))
        return {"points": float(points), "atr_units": float(points/atr),
                "mfe_points": mfe, "mae_points": mae,
                "mfe_atr": mfe/atr, "mae_atr": mae/atr,
                "day": self.days[i], "index": i, "exit_index": exit_}, None

    def control_map(self, signals, eligible):
        # Build from CURRENT bar features only, never from future outcome validity.
        pools = defaultdict(list)
        vol = np.full(len(self.frame), np.nan)
        for i in range(len(self.frame)):
            atr, close = self.prices["atr_14"][i], self.prices["close"][i]
            if _positive(atr) and _positive(close):
                vol[i] = atr/close
                if i not in eligible and isinstance(self.frame.iloc[i].get("story_regime"), str):
                    pools[(self.periods[i], int(self.slots[i]))].append(i)
        matches = {}
        for signal in signals:
            i = signal["index"]
            candidates = []
            if _positive(vol[i]):
                for j in pools[(self.periods[i], int(self.slots[i]))]:
                    age = self.day_ids[self.days[i]] - self.day_ids[self.days[j]]
                    if 1 <= age <= MAX_CONTROL_DAYS:
                        distance = abs(math.log(vol[j]/vol[i]))
                        if distance <= math.log(VOLATILITY_RATIO):
                            candidates.append((distance, -j, j))
            matches[i] = [v[2] for v in sorted(candidates)[:MAX_CONTROLS]]
        return matches


def _non_overlapping_indices(history, cohort, horizon):
    """First signal wins; reserve full horizon even if outcome is invalid."""
    release, selected = -1, set()
    for signal in cohort:
        i = signal["index"]
        if i >= release:
            selected.add(i)
            release = min(i+horizon, int(history.ends[i]))
    return selected


def _matched_estimate(rows, metric):
    """Pair against mean controls, with scores on BOTH actual signal/control days.

    A reused control contributes repeatedly to its own day's score rather than
    being treated as an independent observation on each signal's date.
    """
    pairs = [r for r in rows if r["controls"]]
    if not pairs:
        return {"paired_samples": 0, "control_observations": 0, "unique_control_bars": 0,
                "unique_control_days": 0, "signal_trading_days": 0, "cluster_days": 0,
                "signal_mean": None, "control_mean": None,
                "mean_delta": None, "ci95_day_clustered": None,
                "assessment": "STATISTICALLY_INCONCLUSIVE"}
    signal_values = [r["outcome"][metric] for r in pairs]
    control_values = [float(np.mean([c[metric] for c in r["controls"]])) for r in pairs]
    signal_mean, control_mean = float(np.mean(signal_values)), float(np.mean(control_values))
    scores = defaultdict(float)
    controls = []
    for r in pairs:
        scores[r["outcome"]["day"]] += r["outcome"][metric]-signal_mean
        weight = 1./len(r["controls"])
        for c in r["controls"]:
            scores[c["day"]] -= weight*(c[metric]-control_mean)
            controls.append(c)
    delta = signal_mean-control_mean
    signal_days = len({r["outcome"]["day"] for r in pairs})
    # Many reused/prior control days cannot make five signal days a large sample.
    interval = _cluster_interval(delta, scores, len(pairs)) if signal_days >= MIN_CI_DAYS else None
    return {"paired_samples": len(pairs), "control_observations": len(controls),
            "signal_trading_days": signal_days, "cluster_days": len(scores),
            "unique_control_bars": len({c["index"] for c in controls}),
            "unique_control_days": len({c["day"] for c in controls}),
            "signal_mean": signal_mean, "control_mean": control_mean,
            "mean_delta": delta, "ci95_day_clustered": interval, "assessment": _classify(interval)}


def _summary(records):
    measured = [r for r in records if r["outcome"] is not None]
    unavailable = Counter(r["reason"] for r in records if r["outcome"] is None)
    outcomes = [r["outcome"] for r in measured]
    days = [r["day"] for r in outcomes]
    metrics = {k: _estimate([r[k] for r in outcomes], days) for k in ("points", "atr_units")}
    hit = _estimate([float(r["points"] > 0) for r in outcomes], days)
    opposite = [-r["atr_units"] for r in outcomes]
    opposite_interval = _estimate(opposite, days)["ci95_day_clustered"]
    return {
        "signal_count": len(records), "samples": len(measured), "trading_days": len(set(days)),
        "unavailable_count": sum(unavailable.values()), "unavailable_reasons": dict(unavailable),
        "zero_return_count": sum(r["points"] == 0 for r in outcomes),
        "directional_hit_rate": hit["mean"], "hit_rate_ci95_day_clustered": hit["ci95_day_clustered"],
        "signed_forward_return": metrics,
        "excursions": {k: _distribution([r[k] for r in outcomes])
                       for k in ("mfe_points", "mae_points", "mfe_atr", "mae_atr")},
        "directional_edge": _classify(metrics["atr_units"]["ci95_day_clustered"]),
        "matched_controls": {k: _matched_estimate(measured, k) for k in ("points", "atr_units")},
        "signals_without_predefined_controls": sum(not r["control_indices"] for r in records),
        "control_outcomes_unavailable": sum(r["unavailable_controls"] for r in records),
        "opposite_direction_placebo": {
            "diagnostic_only": True, "samples": len(measured),
            "hit_rate": float(np.mean([r["points"] < 0 for r in outcomes])) if outcomes else None,
            "mean_points": -metrics["points"]["mean"] if outcomes else None,
            "mean_atr_units": float(np.mean(opposite)) if opposite else None,
            "ci95_atr_units": opposite_interval,
        },
    }


def _grouped_summary(records):
    result = _summary(records)
    result["breakdowns"] = {}
    for dimension in DIMENSIONS:
        groups = defaultdict(list)
        for row in records:
            groups[row[dimension]].append(row)
        result["breakdowns"][dimension] = {key: _summary(rows) for key, rows in sorted(groups.items())}
    return result


def audit_symbol(frame, split_at):
    if frame.empty:
        return {"status": "NO_DATA", "story_eligible_signals": 0, "periods": {}}
    history = _History(frame, split_at)
    signals, eligible, reasons = _cohort(history.frame)
    matches = history.control_map(signals, eligible)
    periods = {}
    for period in ("research", "holdout"):
        cohort = [s for s in signals if history.periods[s["index"]] == period]
        horizons = {}
        for horizon in HORIZONS:
            records, cache = [], {}
            selected = _non_overlapping_indices(history, cohort, horizon)
            for signal in cohort:
                i, direction = signal["index"], signal["direction"]
                outcome, reason = history.outcome(i, direction, horizon)
                controls, unavailable_controls = [], 0
                for j in matches[i]:
                    key = (j, direction)
                    if key not in cache:
                        cache[key] = history.outcome(j, direction, horizon)
                    control, _ = cache[key]
                    if control is not None:
                        controls.append(control)
                    else:
                        unavailable_controls += 1
                records.append({**signal, "outcome": outcome, "reason": reason, "controls": controls,
                                "control_indices": matches[i], "unavailable_controls": unavailable_controls})
            non_overlap = [r for r in records if r["index"] in selected]
            horizons[str(horizon)] = {
                "raw_signals": _grouped_summary(records),
                "non_overlapping": {**_grouped_summary(non_overlap),
                                    "overlap_skipped_count": len(records)-len(non_overlap)},
            }
        periods[period] = {"story_eligible_signals": len(cohort), "horizons": horizons}
    return {"status": "SUCCESS" if signals else "NO_STORY_ELIGIBLE_SIGNALS",
            "input_rows": len(history.frame), "story_eligible_signals": len(signals),
            "eligibility_reason_counts": reasons,
            "bars_without_story_labels": int(history.frame.story_regime.isna().sum()), "periods": periods}


def run_story_directional_audit(data=None):
    data = {} if data is None else data
    if not isinstance(data, dict) or set(data)-set(ANCHOR_WINDOW):
        raise ValueError("Only from_date, to_date and holdout_from_date are supported; no parameter search")
    options = {**ANCHOR_WINDOW, **data}
    for key, value in options.items():
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError(f"{key} must be an IST date YYYY-MM-DD")
    start, end = _research_date_window(options["from_date"], options["to_date"])
    split = _research_date_window(options["holdout_from_date"], None)[0]
    if not start < split < end:
        raise ValueError("holdout_from_date must lie inside the date window")
    conn = get_db_conn()
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn:
            query_params = [list(SYMBOLS), "NSE", "5m", start, end]
            diagnostics = _database_read_diagnostics(conn, query_params)
            story_select = ", ".join(f"mc.{k}" for k in STORY_INPUT_COLUMNS)
            frame = read_sql_safe(f"""
                SELECT i.symbol, i.ts, i.open, i.high, i.low, i.close, i.atr_14,
                       mc.market_phase, mc.gap_atr, mc.ema_21_slope, mc.impulse_dir, mc.vwap_dist_pct,
                       {story_select}
                {_COMPARISON_JOIN}
                ORDER BY i.symbol, i.ts
            """, conn, params=query_params)
            diagnostics["after_read_sql_safe"] = _dataframe_story_counts(frame)
            diagnostics["stage_by_symbol"] = _label_loss_stages(diagnostics)
    finally:
        conn.close()
    if "DATAFRAME_RETRIEVAL_MISMATCH" in diagnostics["stage_by_symbol"].values():
        return {"status": "DATA_READ_MISMATCH", "rows_written": 0, "data_read_diagnostics": diagnostics}
    if frame.empty:
        return {"status": "NO_DATA", "rows_written": 0, "data_read_diagnostics": diagnostics}
    symbols = {s: audit_symbol(frame.loc[frame.symbol == s], split) for s in SYMBOLS}
    actual = {s: result["story_eligible_signals"] for s, result in symbols.items()}
    anchored = options == ANCHOR_WINDOW
    parity = actual == EXPECTED_COUNTS if anchored else None
    status = ("COHORT_MISMATCH" if parity is False else
              "SUCCESS" if all(s["status"] == "SUCCESS" and all(p["story_eligible_signals"] for p in s["periods"].values())
                               for s in symbols.values()) else "PARTIAL_DATA")
    return {
        "status": status, "audit_version": AUDIT_VERSION, "research_only": True,
        "exploratory": True, "independent_confirmation_required": True,
        "rows_written": 0, "production_strategy_modified": False,
        "parameter_selection_performed": False, "holdout_used_for_selection": False,
        "date_window": _research_window_metadata(start, end),
        "holdout_from_inclusive": split.isoformat(),
        "cohort_parity": {"anchor_window": anchored, "expected": EXPECTED_COUNTS if anchored else None,
                          "actual": actual, "matches_previous_counterfactual": parity},
        "data_read_diagnostics": diagnostics, "symbols": symbols,
        "methodology": {
            "population": "unchanged existing story resolver and GAP direction; all eligible signals, no production gate filtering",
            "story_thresholds": dict(STORY_TRADE_DEFAULTS), "symbol_exchange_timeframe": "ITC/TATASTEEL NSE 5m",
            "horizons_bars": list(HORIZONS), "reference": "next observed bar open, no costs/slippage applied",
            "outcome": "direction * (close at signal_index+horizon - open at signal_index+1)",
            "normalization": "signal-bar atr_14, frozen; ATR units are not TP/SL R",
            "excursions": "full entry-through-horizon candles; MFE >= 0 and signed MAE <= 0",
            "availability": "require full horizon, same IST day and consecutive 5m candles; never shorten/fill/cross sessions",
            "hit_rate": "signed points > 0 divided by measured samples; zero returns remain in denominator",
            "controls": {"population": "non-eligible bars with stored story context, same symbol/period and exact IST slot",
                         "selection": "up to 3 smallest abs(log ATR/close ratio), ties most recent, within prior 60 trading days",
                         "max_volatility_ratio": VOLATILITY_RATIO, "future_outcomes_used_for_matching": False,
                         "direction": "same as matched story signal; control normalized by its own causal ATR",
                         "reuse": "allowed; counts and day-score covariance account for repeated controls",
                         "missing": "unavailable controls dropped without replacement; no match means no paired delta"},
            "non_overlap": "first signal wins independently per horizon/symbol; reserve through horizon close even for invalid outcomes; signals on exit close allowed",
            "confidence_intervals": "95% asymptotic normal CR1 trading-day score intervals, min 20 signal days; paired scores on signal AND control days; no iid-bar assumption",
            "limitations": "pointwise exploratory intervals, no multiplicity adjustment; dependence across trading days not modeled; matching graph fixed; stored-label historical causality assumed, not revalidated",
            "interpretation": "already-viewed research AND holdout are exploratory; no horizon/direction/threshold selection; independent confirmation requires untouched data or symbols",
            "placebo": "opposite signed outcome on identical bars, diagnostic identity only; not a strategy",
            "unchanged": "story engine, production gates, TP/SL, fee model, ML tables; no simulator or calibration calls",
        },
    }
