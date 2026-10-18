"""Observational safety diagnostics; none of these results authorize a trade."""
import math
from collections import Counter, defaultdict

import numpy as np


SAFETY_AUDIT_GATES = {
    "MACRO_GATE": "macro_gate",
    "PRICE_STRUCTURE_GATE": "price_structure_gate",
    "TREND_EXHAUSTION_GATE": "trend_exhaustion_gate",
    "SIGNAL_DIRECTION_GATE": "signal_direction_gate",
    "COST_GATE": "cost_gate",
    "EOD_GATE": "eod_gate",
    "MIN_RULES_GATE": "min_rules_gate",
}


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _plain(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _pct(count, denominator):
    return round(100.0 * count / denominator, 6) if denominator else None


def _cost_statistics(values, population):
    result = {"count": len(values), "unavailable_count": population - len(values)}
    if not values:
        return {**result, **dict.fromkeys(("min", "max", "mean", "p10", "p25", "p50", "p75", "p90"))}
    # Divide before summing to avoid overflow when finite observations are large.
    mean = float(np.sum(np.asarray(values) / len(values)))
    return {
        **result, "min": min(values), "max": max(values), "mean": _number(mean),
        **{f"p{p}": _number(v) for p, v in zip(
            (10, 25, 50, 75, 90), np.percentile(values, (10, 25, 50, 75, 90))
        )},
    }


def _gate_status(row, prefix):
    if not row[f"{prefix}_applicable"]:
        return "not_applicable"
    value = row[f"{prefix}_pass"]
    return "unavailable" if value is None else "passed" if value else "failed"


class SafetyWaterfallAudit:
    """Aggregate every story-eligible bar, retaining detailed rows only on request.

    Independent checks expose overlapping failures. `reached()` only observes
    actual visits in the unchanged short-circuit loop. `reject()` receives its
    actual first-stop reason; it never selects the reason itself.
    """
    def __init__(self, retain_rows=False):
        self.retain_rows = retain_rows
        self.rows = []
        self.population = 0
        self.accepted = 0
        self.finished = 0
        self.by_setup = Counter()
        self.by_direction = Counter()
        self.rejections = Counter()
        self.rejections_by_setup = defaultdict(Counter)
        self.rejections_by_direction = defaultdict(Counter)
        self.costs = []
        self.costs_by_setup = defaultdict(list)
        self.independent = {gate: Counter() for gate in SAFETY_AUDIT_GATES}
        self.waterfall = {gate: Counter() for gate in SAFETY_AUDIT_GATES}

    def begin(self, *, ts, phase, story, decision, cfg, raw_entry,
              macro, price_structure, exhaustion, signal_open,
              signal_close, bar_of_day, cost_preview,
              eod_bar_threshold, eod_lookahead_threshold, min_rules, rule_count):
        """Evaluate diagnostic predicates without changing execution decisions.

        cost_r aliases the shared componentized pre-trade fee preview. The
        production loop receives that preview independently of this observer.
        Missing inputs remain unknown, never a zero cost or an assumed pass.
        """
        short = decision["trade_direction"] == "SHORT"
        trend_continuation = (
            story["story_regime"] in {"BULL_TREND", "BEAR_TREND"}
            and story["bar_event"] == "CONTINUATION"
        )
        legacy_continuation = phase in {"TREND_CONTINUATION", "BEAR_TREND_CONTINUATION"}
        continuation = trend_continuation or legacy_continuation
        raw_dir = cfg["dir"] if cfg and story["story_regime"] == "GAP_AUCTION" else decision["trade_direction"]
        signal_required = raw_dir in ("LONG", "SHORT", "FOLLOW", "FADE") and bar_of_day != 0
        signal_pass = True
        if signal_required:
            op, close = _number(signal_open), _number(signal_close)
            signal_pass = (None if op is None or close is None else
                           not (close >= op if short else close <= op))

        preview = cost_preview["cost_gate_metric"]
        cost_pass = cost_preview["cost_gate_pass"]

        eod_applicable = bool(cfg and eod_lookahead_threshold > 0
                              and cfg.get("lookahead_min", 0) >= eod_lookahead_threshold)
        row = {
            "ts": ts, "market_phase": _plain(phase),
            **{name: _plain(story.get(name)) for name in (
                "story_regime", "bar_event", "regime_rule_score", "event_rule_score",
                "directional_edge", "regime_age_bars", "candidate_regime",
            )},
            "setup_key": decision["setup_key"], "trade_direction": decision["trade_direction"],
            **cost_preview, "cost_r": preview,
            "entry_price_raw": _number(raw_entry),
            "macro_regime": _plain(macro), "price_structure": _plain(price_structure),
            "trend_exhaustion": _plain(exhaustion),
            "final_eligible": False, "final_skip_reason": None, "gates_reached": [],
        }
        checks = {
            "macro_gate": (True, not ((short and macro == "BULL_MACRO") or
                                      (not short and macro == "BEAR_MACRO"))),
            "price_structure_gate": (continuation, not (continuation and
                price_structure in (("BULL", "TRANSITION") if short else ("BEAR", "TRANSITION")))),
            "trend_exhaustion_gate": (continuation, not (exhaustion == 1 and continuation)),
            "signal_direction_gate": (signal_required, signal_pass),
            "cost_gate": (True, cost_pass),
            "eod_gate": (eod_applicable, not (eod_applicable and bar_of_day >= eod_bar_threshold)),
            "min_rules_gate": (min_rules > 0, not (min_rules > 0 and rule_count < min_rules)),
        }
        for prefix, (applicable, passed) in checks.items():
            row[f"{prefix}_applicable"] = bool(applicable)
            row[f"{prefix}_pass"] = None if passed is None else bool(passed)
        row["independent_failed_gates"] = [
            gate for gate, prefix in SAFETY_AUDIT_GATES.items()
            if _gate_status(row, prefix) == "failed"
        ]
        self.population += 1
        self.by_setup[row["setup_key"]] += 1
        self.by_direction[row["trade_direction"]] += 1
        if preview is not None:
            self.costs.append(preview)
            self.costs_by_setup[row["setup_key"]].append(preview)
        for gate, prefix in SAFETY_AUDIT_GATES.items():
            self.independent[gate][_gate_status(row, prefix)] += 1
        if self.retain_rows:
            self.rows.append(row)
        return row

    def reached(self, row, gate):
        row["gates_reached"].append(gate)
        self.waterfall[gate][_gate_status(row, SAFETY_AUDIT_GATES[gate])] += 1

    def finish(self, row, reason=None):
        if row["final_eligible"] or row["final_skip_reason"] is not None:
            raise RuntimeError("Safety audit row was finalized twice")
        if reason == "COST_GATE":
            assert (row["cost_gate_metric"] is not None
                    and row["cost_gate_metric"] > row["cost_gate_threshold"]
                    and row["cost_gate_pass"] is False), "COST_GATE rejected a passing fee preview"
        self.finished += 1
        row["final_skip_reason"] = reason
        row["final_eligible"] = reason is None
        if reason is None:
            self.accepted += 1
        else:
            self.rejections[reason] += 1
            self.rejections_by_setup[row["setup_key"]][reason] += 1
            self.rejections_by_direction[row["trade_direction"]][reason] += 1

    def summary(self):
        if self.finished != self.population:
            raise RuntimeError("Unfinished story-eligible safety audit rows")
        independent, waterfall = {}, {}
        for gate in SAFETY_AUDIT_GATES:
            independent[gate] = {key: self.independent[gate][key] for key in (
                "passed", "failed", "not_applicable", "unavailable",
            )}
            independent[gate]["failure_pct_of_story_eligible"] = _pct(
                self.independent[gate]["failed"], self.population)
            counts = {key: self.waterfall[gate][key] for key in (
                "passed", "failed", "not_applicable", "unavailable",
            )}
            reached = sum(counts.values())
            waterfall[gate] = {
                **counts, "reached": reached, "not_reached": self.population - reached,
                "failure_pct_of_story_eligible": _pct(counts["failed"], self.population),
            }
        return {
            "final_eligible_trades": self.accepted,
            "final_eligible_pct_of_story_eligible": _pct(self.accepted, self.population),
            "safety_gate_order": list(SAFETY_AUDIT_GATES),
            "safety_pass_fail_counts": independent,
            "safety_waterfall_counts": waterfall,
            "cost_r_statistics": _cost_statistics(self.costs, self.population),
            "cost_r_statistics_by_setup_key": {
                key: _cost_statistics(self.costs_by_setup[key], count)
                for key, count in self.by_setup.items()
            },
            "story_eligible_counts_by_setup_key": dict(self.by_setup),
            "story_eligible_counts_by_direction": dict(self.by_direction),
            "safety_rejection_counts_by_setup_key": {
                key: dict(self.rejections_by_setup[key]) for key in self.by_setup
            },
            "safety_rejection_counts_by_direction": {
                key: dict(self.rejections_by_direction[key]) for key in self.by_direction
            },
            "safety_rejection_pct_of_story_eligible": {
                reason: _pct(count, self.population) for reason, count in self.rejections.items()
            },
            "cost_gate_rejection_pct_of_story_eligible": _pct(self.rejections["COST_GATE"], self.population),
            "cost_gate_rejection_fraction_of_story_eligible": (
                self.rejections["COST_GATE"] / self.population if self.population else None
            ),
            "cost_r_basis": "componentized fee_cost_r_preview; flat exit at slippage-adjusted next-bar entry; no future exit data",
        }
