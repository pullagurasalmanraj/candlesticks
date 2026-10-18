"""Response-only counterfactual research. No database writes or trade authority."""
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from routes.strategy_diagnostics import SAFETY_AUDIT_GATES, _gate_status, _number, _pct
from routes.strategy_costs import (
    COST_BREAKDOWN_FIELDS, COST_MODEL_VERSION, EquityIntradayCostModel, net_r_after_fees,
)
from routes.strategy_logic import (
    SLIPPAGE_PTS, _outcome_excursions, _simulate_exit_vectorized,
)


RESEARCH_COST_BUCKETS = ("<=0.70", "(0.70,1.00]", "(1.00,1.25]", ">1.25")
_OUTCOME_FIELDS = (
    "entry_price", "atr", "risk_points", "cost_r", "exit_price", "exit_reason",
    "exit_after_candles", "exit_ts", "realized_r_gross", "realized_r_net",
    "trade_mfe_r", "trade_mae_r", "horizon_mfe_r", "horizon_mae_r",
    "session_mfe_r", "session_mae_r",
    *COST_BREAKDOWN_FIELDS,
)


def _unavailable(reason):
    return {"simulation_status": "UNAVAILABLE", "simulation_skip_reason": reason}


def _simulate_counterfactual_trade(*, raw_entry, atr, cfg, highs, lows, closes,
                                  timestamps, horizon_n, is_short, cost_model=None):
    """Use the production barrier simulator/cost conventions on a session slice.

    The caller supplies the same effective phase configuration and capped
    lookahead as the production pass. It has already established a same-session
    next-bar entry. No safety thresholds are changed or consulted for admission.
    """
    raw_entry, atr = _number(raw_entry), _number(atr)
    if atr is None or atr <= 0:
        return _unavailable("INVALID_ATR")
    if raw_entry is None or raw_entry <= 0:
        return _unavailable("INVALID_ENTRY")
    sl_multiple, tp_multiple = _number(cfg.get("sl")), _number(cfg.get("tp"))
    if sl_multiple is None or sl_multiple * atr <= 0 or _number(sl_multiple * atr) is None:
        return _unavailable("INVALID_RISK")
    if tp_multiple is None:
        return _unavailable("INVALID_TP")
    available = min(len(highs), len(lows), len(closes), len(timestamps))
    if available < 1 or horizon_n < 1:
        return _unavailable("NO_EXIT_BARS")
    if len({len(highs), len(lows), len(closes), len(timestamps)}) != 1:
        return _unavailable("INCOMPLETE_SESSION_WINDOW")
    if not all(np.isfinite(prices).all() for prices in (highs, lows, closes)):
        return _unavailable("INVALID_FUTURE_PRICES")

    # These are the unchanged production pricing formulas, including adverse
    # entry/TP slippage. SL-first ambiguity remains inside the shared simulator.
    entry = raw_entry + SLIPPAGE_PTS if not is_short else raw_entry - SLIPPAGE_PTS
    if not np.isfinite(entry) or entry <= 0:
        return _unavailable("INVALID_ENTRY")
    if is_short:
        tp = entry - tp_multiple * atr + SLIPPAGE_PTS
        sl = entry + sl_multiple * atr
    else:
        tp = entry + tp_multiple * atr - SLIPPAGE_PTS
        sl = entry - sl_multiple * atr
    risk = abs(entry - sl)
    if not np.isfinite(risk) or risk <= 0:
        return _unavailable("INVALID_RISK")
    if not (np.isfinite(tp) and np.isfinite(sl)):
        return _unavailable("INVALID_BARRIERS")
    horizon_n = min(horizon_n, available)
    exit_reason, exit_price, exit_after, _, _ = _simulate_exit_vectorized(
        entry, tp, sl, highs, lows, closes, horizon_n,
        is_short=is_short, excursion_n=available,
    )
    if exit_after <= 0:
        return _unavailable("NO_EXIT_BARS")
    excursions = _outcome_excursions(entry, highs, lows, exit_after, horizon_n, risk, is_short)
    if exit_reason == "TP_HIT":
        gross = abs(tp - entry) / risk
    elif exit_reason == "SL_HIT":
        gross = -1.0
    else:
        gross = (entry - exit_price if is_short else exit_price - entry) / risk
    try:
        costs = (cost_model or EquityIntradayCostModel()).calculate(
            entry_price=entry, exit_price=exit_price, risk_points=risk, is_short=is_short,
            entry_slippage_pts=abs(entry - raw_entry),
            exit_slippage_pts=SLIPPAGE_PTS if exit_reason == "TP_HIT" else 0.0,
        )
    except ValueError:
        return _unavailable("INVALID_COST_INPUT")
    cost_r = costs["fee_cost_r"]  # compatibility alias; never includes slippage
    net = net_r_after_fees(gross, costs)
    if not all(np.isfinite(value) for value in (gross, cost_r, net, *excursions.values())):
        return _unavailable("NONFINITE_OUTCOME")
    exit_ts = pd.Timestamp(timestamps[int(exit_after) - 1])
    exit_ts = exit_ts.tz_localize("UTC") if exit_ts.tzinfo is None else exit_ts.tz_convert("UTC")
    return {
        "simulation_status": "SIMULATED", "simulation_skip_reason": None,
        "entry_price": float(entry), "atr": float(atr), "risk_points": float(risk),
        "cost_r": float(cost_r), "exit_price": float(exit_price), "exit_reason": exit_reason,
        "exit_after_candles": int(exit_after), "exit_ts": exit_ts.isoformat().replace("+00:00", "Z"),
        "lookahead_candles": int(horizon_n),
        "realized_r_gross": float(gross), "realized_r_net": float(net),
        **costs,
        **{key: float(value) for key, value in excursions.items()},
    }


def _research_statistics(rows):
    completed = [r for r in rows if r["simulation_status"] == "SIMULATED"]
    n = len(completed)
    reasons = Counter(r["exit_reason"] for r in completed)
    result = {
        "N": n, "story_eligible_N": len(rows), "unavailable_N": len(rows) - n,
        "tp_hit_pct": _pct(reasons["TP_HIT"], n),
        "sl_hit_pct": _pct(reasons["SL_HIT"], n),
        "time_exit_pct": _pct(reasons["TIME_EXIT"], n),
    }
    for metric in ("realized_r_gross", "realized_r_net"):
        values = np.asarray([r[metric] for r in completed], dtype=float)
        result[f"avg_{metric}"] = _number(np.sum(values / n)) if n else None
        result[f"median_{metric}"] = _number(np.median(values)) if n else None
    for metric in ("fee_cost_r", "slippage_r", "total_friction_r"):
        values = [r[metric] for r in completed]
        result[metric] = {
            "mean": _number(np.mean(values)) if n else None,
            **dict(zip(("p10", "p25", "p50", "p75", "p90"),
                [_number(v) for v in np.percentile(values, (10, 25, 50, 75, 90))] if n else [None]*5)),
        }
    for metric in ("trade_mfe_r", "trade_mae_r"):
        values = [r[metric] for r in completed]
        result[metric] = dict(zip(("p25", "p50", "p75"),
            [_number(v) for v in np.percentile(values, (25, 50, 75))] if n else [None]*3))
    return result


def _cost_bucket(cost_r):
    # Fixed research reporting bins, not changes to COST_R_MAX_GATE.
    if cost_r <= .70:
        return RESEARCH_COST_BUCKETS[0]
    if cost_r <= 1.00:
        return RESEARCH_COST_BUCKETS[1]
    if cost_r <= 1.25:
        return RESEARCH_COST_BUCKETS[2]
    return RESEARCH_COST_BUCKETS[3]


class CounterfactualResearch:
    def __init__(self):
        self.rows = []

    def add(self, audit, simulation, *, atr=None):
        # Production eligibility was finalized by the real safety waterfall
        # before this research simulation. Future outcomes cannot influence it.
        row = {
            **audit, **dict.fromkeys(_OUTCOME_FIELDS),
            "atr": _number(atr),
            "gate_cost_r": audit["cost_r"], "cost_r_gate": audit["cost_gate_threshold"],
            "production_eligible": audit["final_eligible"],
            "production_skip_reason": audit["final_skip_reason"],
            "is_counterfactual": True,
            "cost_model_version": COST_MODEL_VERSION,
            "fee_breakdown_status": "CALCULATED" if simulation["simulation_status"] == "SIMULATED" else "UNAVAILABLE",
            **simulation,
        }
        self.rows.append(row)

    def summary(self):
        by_setup, by_direction = defaultdict(list), defaultdict(list)
        buckets = {metric: {name: [] for name in RESEARCH_COST_BUCKETS}
                   for metric in ("fee_cost_r", "total_friction_r")}
        for row in self.rows:
            by_setup[row["setup_key"]].append(row)
            by_direction[row["trade_direction"]].append(row)
            if row["simulation_status"] == "SIMULATED":
                for metric, groups in buckets.items():
                    groups[_cost_bucket(row[metric])].append(row)
        gates = {}
        labels = {"passed": "pass", "failed": "fail",
                  "not_applicable": "not_applicable", "unavailable": "unavailable"}
        for _, prefix in SAFETY_AUDIT_GATES.items():
            groups = {label: [] for label in labels.values()}
            for row in self.rows:
                groups[labels[_gate_status(row, prefix)]].append(row)
            gates[f"{prefix}_pass"] = {key: _research_statistics(group) for key, group in groups.items()}
        eligible = [row for row in self.rows if row["production_eligible"]]
        rejected = [row for row in self.rows if not row["production_eligible"]]
        return {
            "total_story_eligible": len(self.rows), "production_eligible": len(eligible),
            "production_rejected": len(rejected),
            "simulated": sum(row["simulation_status"] == "SIMULATED" for row in self.rows),
            "unavailable_simulations": dict(Counter(
                row["simulation_skip_reason"] for row in self.rows if row["simulation_status"] != "SIMULATED"
            )),
            "overall": _research_statistics(self.rows),
            "cost_model_version": COST_MODEL_VERSION,
            "cost_bucket_basis": "cost_r aliases fee_cost_r; total_friction_r includes separately reported execution slippage",
            "cost_buckets": {key: _research_statistics(group) for key, group in buckets["fee_cost_r"].items()},
            "fee_cost_r_buckets": {key: _research_statistics(group) for key, group in buckets["fee_cost_r"].items()},
            "total_friction_r_buckets": {key: _research_statistics(group) for key, group in buckets["total_friction_r"].items()},
            "gate_comparisons": gates,
            "by_setup_key": {key: _research_statistics(group) for key, group in by_setup.items()},
            "by_trade_direction": {key: _research_statistics(group) for key, group in by_direction.items()},
            "by_production_eligibility": {
                "eligible": _research_statistics(eligible), "rejected": _research_statistics(rejected),
            },
        }
