"""Read-only, predefined entry/geometry experiments. Never a production writer."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import math
import re

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, request
from psycopg2 import Error as DatabaseError

from db import get_db_conn, read_sql_safe
from routes.strategy import STORY_INPUT_COLUMNS
from routes.strategy_costs import COST_MODEL_VERSION, EquityIntradayCostModel
from routes.strategy_counterfactual import _simulate_counterfactual_trade
from routes.strategy_dates import _research_date_window, _research_window_metadata
from routes.strategy_logic import (
    PHASE_MODEL, STORY_TRADE_DEFAULTS, _legacy_trade_direction,
    _resolve_story_trade, _story_trade_context,
)


comparison_bp = Blueprint("strategy_comparison", __name__)
COMPARISON_VERSION = "ENTRY_GEOMETRY_RESEARCH_V1"
SYMBOLS = ("ITC", "TATASTEEL")


@dataclass(frozen=True)
class Variant:
    name: str
    family: str = "geometry"
    delay_bars: int = 0
    tp_scale: float = 1.
    sl_scale: float = 1.


# Fixed before observing research or holdout outcomes. No request grid/search.
VARIANTS = (
    Variant("baseline", "baseline"),
    Variant("delay_1", "entry_timing", delay_bars=1),
    Variant("delay_2", "entry_timing", delay_bars=2),
    Variant("tp_0_8x", tp_scale=.8),
    Variant("tp_1_2x", tp_scale=1.2),
    Variant("sl_0_8x", sl_scale=.8),
    Variant("sl_1_2x", sl_scale=1.2),
)
_CALENDAR_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_METRICS = ("realized_r_gross", "realized_r_net", "net_points",
            "trade_mfe", "trade_mae", "trade_mfe_r", "trade_mae_r", "risk_points")


def _mean_median(values):
    if not values:
        return {"avg": None, "median": None}
    values = np.asarray(values, dtype=float)
    return {"avg": float(np.sum(values / len(values))), "median": float(np.median(values))}


def _stats(records):
    busy = [r for r in records if r.get("overlap_skipped")]
    attempted = [r for r in records if not r.get("overlap_skipped")]
    completed = [r for r in attempted if r["status"] == "SIMULATED"]
    missed = Counter(r["reason"] for r in attempted if r["status"] == "MISSED_ENTRY")
    unknown = Counter(r["reason"] for r in attempted if r["status"] == "OUTCOME_UNAVAILABLE")
    n = len(completed)
    exits = Counter(r["exit_reason"] for r in completed)
    assert n + sum(missed.values()) + sum(unknown.values()) + len(busy) == len(records)
    return {
        "story_signal_count": len(records), "samples": n,
        "overlap_skipped_count": len(busy),
        "missed_entry_count": sum(missed.values()), "missed_entry_reasons": dict(missed),
        "unavailable_outcome_count": sum(unknown.values()), "unavailable_outcome_reasons": dict(unknown),
        "tp_pct": 100.*exits["TP_HIT"]/n if n else None,
        "sl_pct": 100.*exits["SL_HIT"]/n if n else None,
        "time_exit_pct": 100.*exits["TIME_EXIT"]/n if n else None,
        **{key: _mean_median([r[key] for r in completed]) for key in _METRICS},
    }


def _grouped_stats(records):
    groups = defaultdict(list)
    for row in records:
        groups[row["setup_key"]].append(row)
    return {**_stats(records), "by_setup_key": {k: _stats(v) for k, v in sorted(groups.items())}}


def _non_overlapping(records):
    """First signal wins per symbol; reserve pending entries as well as positions.

    Release is processed only when the historical bar closes at/after the
    recorded exit. Same-exit-bar signals can schedule a *next*-bar entry.
    Missing delayed entries reserve until session close. Future unavailability
    cannot cause an earlier signal to be discarded in favor of a later winner.
    """
    selected = []
    release_at = -1
    pending_until = -1
    pending_skips = 0
    for row in records:
        busy = row["signal_index"] < release_at
        selected.append({**row, "overlap_skipped": busy})
        if busy:
            pending_skips += row["signal_index"] < pending_until
        else:
            release_at = row["release_index"]
            pending_until = row.get("entry_index", release_at)
    return selected, {"pending_order_skips": int(pending_skips)}


def _overlap_flags(records):
    # Flag every trade in an intersecting group, not just later entrants.
    trades = sorted((r for r in records if r["status"] == "SIMULATED"), key=lambda r: r["entry_index"])
    overlapping, group_size, group_end = 0, 0, -1
    events = Counter()
    for row in trades:
        if row["entry_index"] > group_end:
            overlapping += group_size if group_size > 1 else 0
            group_size = 0
        group_size += 1
        group_end = max(group_end, row["exit_index"])
        events[row["entry_index"]] += 1
        events[row["exit_index"] + 1] -= 1
    overlapping += group_size if group_size > 1 else 0
    active, maximum = 0, 0
    for index in sorted(events):
        active += events[index]
        maximum = max(maximum, active)
    release_at = -1
    signal_overlaps = 0
    for row in records:
        signal_overlaps += row["signal_index"] < release_at
        release_at = max(release_at, row["release_index"])
    return {"overlapping_trade_count": overlapping, "max_concurrent_trades": maximum,
            "signals_while_prior_signal_pending_or_active": int(signal_overlaps)}


def _paired_delta(baseline, variant):
    def completed(rows):
        return {r["signal_index"]: r for r in rows
                if r["status"] == "SIMULATED" and not r.get("overlap_skipped")}
    before, after = completed(baseline), completed(variant)
    common = sorted(before.keys() & after.keys())
    return {
        "paired_samples": len(common), "baseline_only_samples": len(before.keys() - after.keys()),
        "variant_only_samples": len(after.keys() - before.keys()),
        **{f"delta_{metric}": _mean_median([after[k][metric]-before[k][metric] for k in common])
           for metric in ("realized_r_gross", "realized_r_net", "net_points")},
    }


def _effective_params(params, from_dt):
    """Freeze current settings for BOTH periods, preserving overlap protection."""
    trusted, ignored = {}, Counter()
    overlap = False
    for phase, info in params.items():
        try:
            calibrated_to = pd.Timestamp(info.get("calibrated_to"))
            if pd.isna(calibrated_to):
                raise ValueError("Unknown calibration end")
            calibrated_to = (calibrated_to.tz_localize("UTC") if calibrated_to.tzinfo is None
                             else calibrated_to.tz_convert("UTC"))
        except (ValueError, TypeError, OverflowError):
            ignored["unknown_calibration_window"] += 1
            continue
        overlap |= from_dt <= calibrated_to
        try:
            if not all(math.isfinite(float(info[key])) and float(info[key]) > 0
                       for key in ("tp", "sl", "lookahead_min")):
                raise ValueError("Invalid parameters")
        except (ValueError, TypeError, KeyError):
            ignored["invalid_calibrated_parameters"] += 1
            continue
        trusted[phase] = info
    if overlap:
        trusted = {}
    configs = {}
    for phase, defaults in PHASE_MODEL.items():
        cfg = dict(defaults)
        info = trusted.get(phase)
        source = "default"
        if info:
            if info.get("viable", True):
                cfg.update(tp=info["tp"], sl=info["sl"], lookahead_min=info["lookahead_min"])
                source = "calibrated"
            else:
                source = "default_unviable_fallback"
        cfg["source"] = source
        cfg["lookahead_bars"] = max(2, min(375, math.ceil(cfg.get("lookahead_min", 30)/5)))
        configs[phase] = cfg
    return configs, {"overlapping_calibration_ignored": overlap,
                     "ignored_calibration_rows": dict(ignored),
                     "baseline_frozen_for_both_periods": True,
                     "defaults_provenance": "current PHASE_MODEL; historical fitting provenance is not available"}


def _prepare_frame(frame):
    if frame.empty:
        return frame.copy()
    frame = frame.copy()
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce")
    if frame["ts"].isna().any() or frame["ts"].duplicated().any():
        raise ValueError("OHLCV/story join must have unique, valid timestamps per symbol")
    return frame.sort_values("ts").reset_index(drop=True)


def compare_symbol(frame, *, split_at, from_dt, params, cost_model):
    """All rows remain in memory only; return bounded aggregates, never audits."""
    frame = _prepare_frame(frame)
    if frame.empty:
        return {"status": "NO_DATA", "input_rows": 0, "periods": {}}
    configs, provenance = _effective_params(params, from_dt)
    dates = frame["ts"].dt.tz_convert("Asia/Kolkata").dt.date.to_numpy()
    n = len(frame)
    ends = np.empty(n, dtype=int)
    last = n-1
    for i in range(n-1, -1, -1):
        if i == n-1 or dates[i] != dates[i+1]:
            last = i
        ends[i] = last
    prices = {key: pd.to_numeric(frame[key], errors="coerce").to_numpy(dtype=float)
              for key in ("open", "high", "low", "close", "atr_14")}
    times = frame["ts"].tolist()
    signals, reasons = [], Counter()
    for i, row in enumerate(frame.to_dict("records")):
        cfg = configs.get(row.get("market_phase"))
        story = _story_trade_context({k: row.get(k) for k in STORY_INPUT_COLUMNS})
        gap_direction = None
        if story["story_regime"] == "GAP_AUCTION" and cfg:
            gap_direction = _legacy_trade_direction(cfg["dir"], row.get("gap_atr"), row.get("ema_21_slope"),
                                                     row.get("impulse_dir"), row.get("vwap_dist_pct"))
        decision = _resolve_story_trade(story, gap_direction=gap_direction)
        reasons[decision["eligibility_reason"]] += 1
        if decision["eligible"]:
            signals.append({"signal_index": i, "setup_key": decision["setup_key"],
                            "short": decision["trade_direction"] == "SHORT", "cfg": cfg,
                            "phase": row.get("market_phase")})

    def simulate(signal, variant):
        i = signal["signal_index"]
        cfg = signal["cfg"]
        entry = i + 1 + variant.delay_bars
        row = {"signal_index": i, "setup_key": signal["setup_key"], "release_index": i}

        def missing(reason, *, until=None, entered=False):
            return {**row, "status": "OUTCOME_UNAVAILABLE" if entered else "MISSED_ENTRY",
                    "reason": reason, "release_index": i if until is None else until}

        if not cfg:
            return missing("MISSING_PHASE_CONFIG")
        atr = prices["atr_14"][i]  # frozen at signal, never delayed-bar ATR/story
        if not math.isfinite(atr) or atr <= 0:
            return missing("INVALID_SIGNAL_ATR")
        if entry >= n or dates[entry] != dates[i]:
            return missing("NO_SAME_SESSION_ENTRY", until=int(ends[i]))
        row["entry_index"] = entry
        raw_entry = prices["open"][entry]
        if not math.isfinite(raw_entry) or raw_entry <= 0:
            return missing("INVALID_ENTRY_OPEN", until=entry)
        cfg = {**cfg, "tp": cfg["tp"]*variant.tp_scale, "sl": cfg["sl"]*variant.sl_scale}
        if not all(math.isfinite(cfg[k]) and cfg[k] > 0 for k in ("tp", "sl")):
            return missing("INVALID_GEOMETRY")
        stop = int(ends[entry])+1
        outcome = _simulate_counterfactual_trade(
            raw_entry=raw_entry, atr=atr, cfg=cfg,
            highs=prices["high"][entry:stop], lows=prices["low"][entry:stop],
            closes=prices["close"][entry:stop], timestamps=times[entry:stop],
            horizon_n=min(cfg["lookahead_bars"], stop-entry), is_short=signal["short"], cost_model=cost_model,
        )
        if outcome["simulation_status"] != "SIMULATED":
            reason = outcome["simulation_skip_reason"]
            entry_invalid = reason in {"INVALID_ENTRY", "INVALID_RISK", "INVALID_TP", "INVALID_BARRIERS"}
            return missing(reason, until=entry if entry_invalid else stop-1, entered=not entry_invalid)
        exit_index = entry+outcome["exit_after_candles"]-1
        assert dates[i] == dates[entry] == dates[exit_index]
        assert (times[i] < split_at) == (times[exit_index] < split_at), "Period-boundary leakage"
        return {**row, "status": "SIMULATED", "reason": None, "exit_index": exit_index,
                "release_index": exit_index,
                **{key: outcome[key] for key in _METRICS if key != "net_points"},
                "net_points": outcome["realized_r_net"]*outcome["risk_points"],
                "exit_reason": outcome["exit_reason"]}

    periods = {}
    for period, before in (("research", True), ("holdout", False)):
        cohort = [s for s in signals if (times[s["signal_index"]] < split_at) == before]
        variants = {}
        baseline_raw = baseline_execution = None
        for variant in VARIANTS:
            records = [simulate(s, variant) for s in cohort]
            execution, execution_notes = _non_overlapping(records)
            if variant.name == "baseline":
                baseline_raw, baseline_execution = records, execution
            variants[variant.name] = {
                "raw_signals": _grouped_stats(records),
                "non_overlapping": {**_grouped_stats(execution), **execution_notes},
                "overlap_flags": _overlap_flags(records),
                "paired_vs_baseline": {
                    "raw_signals": _paired_delta(baseline_raw, records),
                    "non_overlapping": _paired_delta(baseline_execution, execution),
                },
            }
        available_rows = [i for i in range(n) if (times[i] < split_at) == before]
        periods[period] = {
            "input_rows": len(available_rows), "story_eligible_signals": len(cohort),
            "first_bar_ts": times[available_rows[0]].isoformat() if available_rows else None,
            "last_bar_ts": times[available_rows[-1]].isoformat() if available_rows else None,
            "first_signal_ts": times[cohort[0]["signal_index"]].isoformat() if cohort else None,
            "last_signal_ts": times[cohort[-1]["signal_index"]].isoformat() if cohort else None,
            "variants": variants,
        }
    gaps = sum(dates[i] == dates[i-1] and times[i]-times[i-1] != pd.Timedelta(minutes=5) for i in range(1, n))
    session_edges = frame.groupby(frame["ts"].dt.tz_convert("Asia/Kolkata").dt.date)["ts"].agg(["min", "max"])
    incomplete = sum(row["min"].tz_convert("Asia/Kolkata").strftime("%H:%M") != "09:15"
                     or row["max"].tz_convert("Asia/Kolkata").strftime("%H:%M") != "15:25"
                     for row in session_edges.to_dict("records"))
    used = sorted({s["phase"] for s in signals if s["cfg"]})
    status = ("INSUFFICIENT_PERIOD_DATA" if not all(p["input_rows"] for p in periods.values()) else
              "NO_STORY_ELIGIBLE_SIGNALS" if not signals else
              "INSUFFICIENT_STORY_SIGNALS" if not all(p["story_eligible_signals"] for p in periods.values()) else "SUCCESS")
    return {
        "status": status,
        "input_rows": n, "eligibility_reason_counts": dict(reasons),
        "first_bar_ts": times[0].isoformat(), "last_bar_ts": times[-1].isoformat(),
        "trading_days": len(set(dates)),
        "data_quality": {"non_5m_gaps_within_session": int(gaps),
                         "sessions_not_spanning_0915_to_1525_IST": int(incomplete),
                         "bars_without_story_labels": int(frame["story_regime"].isna().sum())},
        "baseline_parameters": {p: {k: configs[p].get(k) for k in ("tp", "sl", "lookahead_min", "lookahead_bars", "source")}
                                for p in used},
        "parameter_provenance": provenance, "periods": periods,
    }


def _request_options(data):
    allowed = {"from_date", "to_date", "holdout_from_date", "cost_model", "symbols", "timeframe", "exchange"}
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    unknown = sorted(set(data)-allowed)
    if unknown:
        raise ValueError(
            f"Unsupported fields: {', '.join(unknown)}. "
            f"Allowed fields: {', '.join(sorted(allowed))}. "
            "Use symbols: [ITC, TATASTEEL], not symbol; diagnostic_mode, counterfactual_mode "
            "and TP/SL overrides belong to other requests, not this fixed research comparison."
        )
    if data.get("symbols", list(SYMBOLS)) != list(SYMBOLS) or data.get("timeframe", "5m") != "5m" or data.get("exchange", "NSE") != "NSE":
        raise ValueError("This predefined comparison is for symbols [ITC, TATASTEEL], NSE, 5m")
    for key in ("from_date", "to_date", "holdout_from_date"):
        if key in data and (not isinstance(data[key], str) or not _CALENDAR_DAY.fullmatch(data[key])):
            raise ValueError(f"{key} must be an IST calendar date YYYY-MM-DD")
    start, end = _research_date_window(data.get("from_date"), data.get("to_date"))
    # Split only at calendar-day boundaries; no labels can span periods.
    split = _research_date_window(data["holdout_from_date"], None)[0] if data.get("holdout_from_date") else None
    if split is not None and not start < split < end:
        raise ValueError("holdout_from_date must lie inside the requested date window")
    return start, end, split, EquityIntradayCostModel.from_request(data.get("cost_model", {}))


def run_entry_geometry_comparison(data):
    start, end, split, cost_model = _request_options(data)
    conn = get_db_conn()
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn:
            columns = read_sql_safe("""
                SELECT c.relname AS table_name, a.attname AS column_name
                FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
                WHERE a.attrelid IN (to_regclass('market_context'), to_regclass('phase_params'))
                  AND a.attnum>0 AND NOT a.attisdropped
            """, conn)
            present = set(columns.loc[columns.table_name == "market_context", "column_name"]) if not columns.empty else set()
            missing = sorted(set(STORY_INPUT_COLUMNS)-present)
            if missing:
                return {"status": "MISSING_STORY_SCHEMA", "missing_columns": missing, "rows_written": 0}
            story_select = ", ".join(f"mc.{k}" for k in STORY_INPUT_COLUMNS)
            frame = read_sql_safe(f"""
                SELECT i.symbol, i.ts, i.open, i.high, i.low, i.close, i.volume, i.atr_14,
                       mc.market_phase, mc.gap_atr, mc.ema_21_slope, mc.impulse_dir, mc.vwap_dist_pct,
                       {story_select}
                FROM indicators i LEFT JOIN market_context mc
                  ON mc.symbol=i.symbol AND mc.exchange=i.exchange AND mc.timeframe=i.timeframe AND mc.ts=i.ts
                WHERE i.symbol=ANY(%s) AND i.exchange=%s AND i.timeframe=%s AND i.ts >= %s AND i.ts < %s
                ORDER BY i.symbol, i.ts
            """, conn, params=[list(SYMBOLS), "NSE", "5m", start, end])
            available = set(columns.loc[columns.table_name == "phase_params", "column_name"]) if not columns.empty else set()
            required = {"symbol", "exchange", "timeframe", "market_phase", "optimal_tp", "optimal_sl",
                        "optimal_lookahead_min", "viable", "calibrated_from", "calibrated_to"}
            params = read_sql_safe("""
                SELECT symbol, market_phase, optimal_tp, optimal_sl, optimal_lookahead_min, viable,
                       calibrated_from, calibrated_to FROM phase_params
                WHERE symbol=ANY(%s) AND exchange=%s AND timeframe=%s
            """, conn, params=[list(SYMBOLS), "NSE", "5m"]) if required <= available else pd.DataFrame()
    finally:
        conn.close()
    if frame.empty:
        return {"status": "NO_DATA", "rows_written": 0, "symbols": list(SYMBOLS), "timeframe": "5m"}
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    days = sorted(frame.ts.dt.tz_convert("Asia/Kolkata").dt.date.unique())
    if split is None:
        if len(days) < 2:
            return {"status": "INSUFFICIENT_SPLIT_DATA", "trading_days": len(days), "rows_written": 0}
        research_days = max(1, min(len(days)-1, math.floor(.7*len(days))))
        split = pd.Timestamp(days[research_days]).tz_localize("Asia/Kolkata").tz_convert("UTC")
    by_symbol = {}
    for symbol in SYMBOLS:
        symbol_params = {}
        if not params.empty:
            for row in params.loc[params.symbol == symbol].to_dict("records"):
                symbol_params[row["market_phase"]] = {
                    "tp": row["optimal_tp"], "sl": row["optimal_sl"],
                    "lookahead_min": row["optimal_lookahead_min"],
                    "viable": True if pd.isna(row["viable"]) else bool(row["viable"]),
                    "calibrated_to": None if pd.isna(row["calibrated_to"]) else row["calibrated_to"],
                }
        by_symbol[symbol] = compare_symbol(frame.loc[frame.symbol == symbol], split_at=split, from_dt=start,
                                           params=symbol_params, cost_model=cost_model)
    return {
        "status": "SUCCESS" if all(s["status"] == "SUCCESS" for s in by_symbol.values()) else "PARTIAL_DATA",
        "research_only": True, "comparison_version": COMPARISON_VERSION,
        "rows_written": 0, "production_strategy_modified": False, "holdout_used_for_selection": False,
        "parameter_selection_performed": False, "timeframe": "5m", "symbols": by_symbol,
        "date_window": _research_window_metadata(start, end),
        "split": {"research_from_inclusive": start.isoformat(), "research_to_exclusive": split.isoformat(),
                  "holdout_from_inclusive": split.isoformat(), "holdout_to_exclusive": end.isoformat(),
                  "basis": "shared IST trading-day chronology; default earliest 70%, latest 30%"},
        "variants": [asdict(v) for v in VARIANTS], "cost_model_version": COST_MODEL_VERSION,
        "calibration_schema_available": required <= available,
        "cost_model": cost_model.metadata(),
        "methodology": {
            "population": "all story-eligible signals, same frozen direction and signal ATR for every variant",
            "story_policy": dict(STORY_TRADE_DEFAULTS),
            "safety_gates": "not used to filter research samples; production gates are untouched",
            "entry": "signal index + 1 + delay, at observed bar open; no price-dependent entry selection",
            "bar_clock": "observed bars; missing five-minute intervals flagged, never filled",
            "lookahead": "unchanged configured bar count starting at variant entry; capped at same IST session end",
            "non_overlap": "one pending order/position per symbol; chronological first signal wins; exit-bar close frees slot",
            "portfolio": "per-symbol execution approximation, not a shared-capital two-symbol portfolio",
            "percent_denominators": "TP/SL/TIME use samples; missed and skipped counts use the same story-signal cohort",
            "geometry": "relative multipliers of frozen current phase TP/SL; entry held at baseline timing",
            "interpretation": "compare research paired deltas, then inspect untouched holdout separately; no best variant chosen",
            "risk_units": "SL geometry changes the R denominator; net points are also reported to expose rescaling",
            "interaction": "joint delay x geometry combinations are not tested",
        },
    }


@comparison_bp.route("/api/offline/compare-entry-geometry", methods=["POST"])
def compare_entry_geometry():
    try:
        result = run_entry_geometry_comparison(request.get_json(silent=False) or {})
        return jsonify(result), 409 if result["status"] == "MISSING_STORY_SCHEMA" else 200
    except ValueError as exc:
        return jsonify({"error": str(exc), "rows_written": 0}), 400
    except DatabaseError:
        return jsonify({"error": "Research database unavailable; no data was written", "rows_written": 0}), 503
