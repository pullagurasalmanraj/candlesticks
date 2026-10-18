"""Research outcomes must never change production eligibility or persistence."""
import copy
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import test_story_outcomes as fixtures  # noqa: E402
from routes.strategy_counterfactual import (  # noqa: E402
    CounterfactualResearch, _simulate_counterfactual_trade,
)


class TestCounterfactualRoute(unittest.TestCase):
    def setUp(self):
        self.route = fixtures.TestStoryOutcomeRoute()
        self.route.setUp()

    def test_every_safety_failure_is_simulated_without_production_writes(self):
        for changes, parameters, reason in (
            ({"macro_regime": "BEAR_MACRO"}, {}, "MACRO_MISMATCH"),
            ({"price_structure": "BEAR"}, {}, "PRICE_STRUCTURE_MISMATCH"),
            ({"trend_exhaustion": 1}, {}, "TREND_EXHAUSTED"),
            ({"close": 99.}, {}, "SIGNAL_DIRECTION_MISMATCH"),
            ({"atr_14": .1}, {}, "COST_GATE"),
            ({"minute_of_day_mc": 320}, {}, "EOD_GATE"),
            ({}, {"min_rules_fired": 1}, "MIN_RULES_GATE"),
        ):
            with self.subTest(reason=reason):
                response = self.route.run_route(self.route.frame(**changes), {
                    **parameters, "counterfactual_mode": True,
                })
                self.assertEqual(response.status_code, 200, response.json)
                data = response.json
                self.assertTrue(data["counterfactual_mode"])
                self.assertTrue(data["production_rules_unchanged"])
                self.assertEqual(data["rows_written"], 0)
                self.assertEqual(data["eligible_trades"], 0)
                self.assertEqual(data["counterfactual_outcomes_generated"], 1)
                research = data["counterfactual_rows"][0]
                self.assertFalse(research["production_eligible"])
                self.assertEqual(research["production_skip_reason"], reason)
                self.assertEqual(research["simulation_status"], "SIMULATED")
                self.assertTrue(research["is_counterfactual"])
                self.assertAlmostEqual(research["realized_r_gross"] - research["cost_r"], research["realized_r_net"])
                summary = data["counterfactual_summary"]
                self.assertEqual(summary["production_rejected"], 1)
                self.assertEqual(summary["production_eligible"], 0)
                self.assertEqual(summary["simulated"], 1)
        self.route.cur.execute.assert_not_called()
        self.assertEqual(self.route.written, [])

    def test_accepted_simulation_matches_production_exactly(self):
        response = self.route.run_route()
        self.assertEqual(response.status_code, 200, response.json)
        production = copy.deepcopy(self.route.written[0])
        self.route.cur.execute.reset_mock()
        response = self.route.run_route(params={"counterfactual_mode": True})
        data = response.json
        row = data["counterfactual_rows"][0]
        self.assertTrue(row["production_eligible"])
        self.assertIsNone(row["production_skip_reason"])
        for name in ("exit_reason", "exit_after_candles", "cost_r", "realized_r_gross",
                     "trade_mfe_r", "trade_mae_r", "horizon_mfe_r", "horizon_mae_r",
                     "session_mfe_r", "session_mae_r"):
            self.assertEqual(row[name], production[name], name)
        self.assertEqual(row["realized_r_net"], production["realized_r"])
        self.assertEqual(pd.Timestamp(row["exit_ts"]).tz_localize(None), production["exit_ts"])
        self.assertAlmostEqual(row["entry_price"], 100.05)
        self.assertAlmostEqual(row["gate_cost_r"], .15)
        self.assertNotEqual(row["gate_cost_r"], row["cost_r"])
        self.route.cur.execute.assert_not_called()
        self.assertEqual(len(self.route.written), 1)  # only the earlier normal request wrote

    def test_all_story_eligible_rows_are_retained_even_when_unsimulatable(self):
        for changes, reason in (({"atr_14": 0.}, "INVALID_ATR"),
                                ({"atr_14": np.nan}, "INVALID_ATR")):
            with self.subTest(reason=reason):
                response = self.route.run_route(self.route.frame(**changes), {"counterfactual_mode": True})
                row = response.json["counterfactual_rows"][0]
                self.assertEqual(row["simulation_status"], "UNAVAILABLE")
                self.assertEqual(row["simulation_skip_reason"], reason)
                self.assertIsNone(row["realized_r_net"])
                self.assertEqual(response.json["counterfactual_summary"]["overall"]["N"], 0)
                self.assertEqual(response.json["counterfactual_summary"]["total_story_eligible"], 1)
        frame = self.route.frame()
        frame.loc[0, "story_regime"] = "TRANSITION"
        frame.loc[[11, 12], "story_regime"] = "BULL_TREND"
        response = self.route.run_route(frame, {"counterfactual_mode": True})
        rows = response.json["counterfactual_rows"]
        self.assertEqual([r["simulation_skip_reason"] for r in rows], ["NEXT_BAR_OUTSIDE_SESSION", "NO_NEXT_BAR"])
        self.assertEqual(response.json["counterfactual_summary"]["simulated"], 0)
        self.route.cur.execute.assert_not_called()

    def test_session_excursion_and_exit_never_use_next_day(self):
        response = self.route.run_route(self.route.frame(macro_regime="BEAR_MACRO"), {"counterfactual_mode": True})
        row = response.json["counterfactual_rows"][0]
        self.assertEqual(row["exit_after_candles"], 1)
        self.assertAlmostEqual(row["trade_mae_r"], -.55)
        self.assertAlmostEqual(row["horizon_mae_r"], -3.05)
        self.assertAlmostEqual(row["session_mae_r"], -10.05)
        self.assertEqual(pd.Timestamp(row["exit_ts"]), pd.Timestamp("2026-10-16T04:05Z"))

    def test_short_direction_is_story_authority_even_when_macro_rejects(self):
        response = self.route.run_route(self.route.frame(
            story_regime="BEAR_TREND", candidate_regime="BEAR_TREND",
            market_phase="TREND_ACCEPTANCE", price_structure="BEAR", close=99.,
            macro_regime="BULL_MACRO", reason_details={"directional_edge": -.65},
        ), {"counterfactual_mode": True})
        row = response.json["counterfactual_rows"][0]
        self.assertEqual(row["trade_direction"], "SHORT")
        self.assertEqual(row["production_skip_reason"], "MACRO_MISMATCH")
        self.assertAlmostEqual(row["entry_price"], 99.95)
        self.assertEqual(row["simulation_status"], "SIMULATED")

    def test_future_outcomes_cannot_change_eligibility(self):
        first = self.route.run_route(params={"counterfactual_mode": True}).json["counterfactual_rows"][0]
        frame = self.route.frame()
        frame.loc[1, ["high", "low"]] = [100.5, 98.]
        second = self.route.run_route(frame, {"counterfactual_mode": True}).json["counterfactual_rows"][0]
        self.assertNotEqual(first["exit_reason"], second["exit_reason"])
        for name in ("production_eligible", "production_skip_reason", "independent_failed_gates",
                     "macro_gate_pass", "price_structure_gate_pass", "signal_direction_gate_pass",
                     "trend_exhaustion_gate_pass", "cost_gate_pass", "eod_gate_pass", "min_rules_gate_pass"):
            self.assertEqual(first[name], second[name], name)

    def test_diagnostic_mode_is_unchanged_and_can_be_combined(self):
        diagnostic = self.route.run_route(params={"diagnostic_mode": True}).json
        self.assertEqual(diagnostic["status"], "DIAGNOSTIC")
        self.assertNotIn("counterfactual_rows", diagnostic)
        combined = self.route.run_route(params={"diagnostic_mode": True, "counterfactual_mode": True}).json
        self.assertEqual(combined["audit_rows"], diagnostic["audit_rows"])
        self.assertEqual(combined["skipped_by_safety"], diagnostic["skipped_by_safety"])
        self.assertEqual(len(combined["counterfactual_rows"]), 1)
        self.route.cur.execute.assert_not_called()

    def test_counterfactual_flag_is_strict_boolean(self):
        for value in ("true", "false", 1, [], None):
            with self.subTest(value=value), patch.object(fixtures.strategy, "get_db_conn") as db:
                response = self.route.client.post("/api/offline/calc-strategy-outcomes", json={
                    "symbol": "ITC", "timeframe": "5m", "counterfactual_mode": value,
                })
                self.assertEqual(response.status_code, 400)
                db.assert_not_called()

    def test_no_story_eligible_setups_returns_empty_research(self):
        frame = self.route.frame()
        frame["story_regime"] = "TRANSITION"
        response = self.route.run_route(frame, {"counterfactual_mode": True})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["counterfactual_rows"], [])
        self.assertEqual(response.json["counterfactual_summary"]["total_story_eligible"], 0)
        self.assertIsNone(response.json["counterfactual_summary"]["overall"]["avg_realized_r_net"])


class TestCounterfactualSimulatorAndStatistics(unittest.TestCase):
    def simulate(self, short=False, **changes):
        arguments = {
            "raw_entry": 100., "atr": 1., "cfg": {"tp": 1., "sl": 1.},
            "highs": np.array([103., 105., 110.]), "lows": np.array([99.5, 97., 90.]),
            "closes": np.array([101., 100., 99.]),
            "timestamps": pd.date_range("2026-10-16T04:05Z", periods=3, freq="5min"),
            "horizon_n": 2, "is_short": short,
        }
        arguments.update(changes)
        return _simulate_counterfactual_trade(**arguments)

    def test_short_excursions_and_sl_first_ties(self):
        result = self.simulate(True, highs=np.array([100.5, 105., 110.]), lows=np.array([98.5, 95., 90.]))
        self.assertEqual(result["exit_reason"], "TP_HIT")
        self.assertAlmostEqual(result["trade_mae_r"], -.55)
        self.assertAlmostEqual(result["horizon_mae_r"], -5.05)
        self.assertAlmostEqual(result["session_mae_r"], -10.05)
        for short in (False, True):
            result = self.simulate(short, highs=np.array([103., 103., 103.]), lows=np.array([97., 97., 97.]))
            self.assertEqual(result["exit_reason"], "SL_HIT")
            self.assertEqual(result["realized_r_gross"], -1)

    def test_time_exit_uses_configured_horizon_and_costs(self):
        result = self.simulate(cfg={"tp": 2., "sl": 2.}, highs=np.array([100.4, 100.5, 110.]),
                               lows=np.array([99.7, 99.8, 90.]), closes=np.array([100., 100.2, 100.]))
        self.assertEqual(result["exit_reason"], "TIME_EXIT")
        self.assertEqual(result["exit_after_candles"], 2)
        self.assertEqual(pd.Timestamp(result["exit_ts"]), pd.Timestamp("2026-10-16T04:10Z"))
        self.assertAlmostEqual(result["realized_r_gross"], (100.2-100.05)/2)
        self.assertAlmostEqual(result["realized_r_net"], result["realized_r_gross"]-result["cost_r"])

    def test_cost_bucket_boundaries_grouping_and_quantiles(self):
        route = fixtures.TestStoryOutcomeRoute()
        route.setUp()
        audit = route.run_route(params={"diagnostic_mode": True}).json["audit_rows"][0]
        research = CounterfactualResearch()
        costs = [.70, .700001, 1., 1.000001, 1.25, 1.250001]
        net = [1., -1., 0., 2., -2., -.5]
        for i, cost in enumerate(costs):
            source = copy.deepcopy(audit)
            source.update(setup_key="BULL:CONTINUATION:LONG" if i % 2 == 0 else "BEAR:ACCEPTANCE:SHORT",
                          trade_direction="LONG" if i % 2 == 0 else "SHORT",
                          final_eligible=i % 2 == 0, final_skip_reason=None if i % 2 == 0 else "COST_GATE",
                          cost_gate_pass=cost <= .70)
            if i == 4:
                source["price_structure_gate_applicable"] = False
            if i == 5:
                source["signal_direction_gate_pass"] = None
            research.add(source, {
                "simulation_status": "SIMULATED", "simulation_skip_reason": None,
                "cost_r": cost, "exit_reason": ("TP_HIT", "SL_HIT", "TIME_EXIT")[i % 3],
                "realized_r_net": net[i], "realized_r_gross": net[i]+cost,
                "trade_mfe_r": i+1., "trade_mae_r": -(i+1)/10,
            })
        missing = copy.deepcopy(audit)
        missing.update(final_eligible=False, final_skip_reason="INVALID_ATR")
        research.add(missing, {"simulation_status": "UNAVAILABLE", "simulation_skip_reason": "INVALID_ATR"})
        summary = research.summary()
        self.assertEqual(summary["total_story_eligible"], 7)
        self.assertEqual(summary["simulated"], 6)
        self.assertEqual([group["N"] for group in summary["cost_buckets"].values()], [1, 2, 2, 1])
        self.assertAlmostEqual(summary["overall"]["avg_realized_r_net"], np.mean(net))
        self.assertAlmostEqual(summary["overall"]["median_realized_r_net"], -.25)
        self.assertAlmostEqual(summary["overall"]["tp_hit_pct"], 100/3, places=5)
        self.assertAlmostEqual(summary["overall"]["trade_mfe_r"]["p25"], 2.25)
        self.assertAlmostEqual(summary["overall"]["trade_mae_r"]["p50"], -.35)
        self.assertEqual(summary["by_trade_direction"]["LONG"]["N"], 3)
        self.assertEqual(summary["by_trade_direction"]["SHORT"]["N"], 3)
        self.assertEqual(summary["unavailable_simulations"], {"INVALID_ATR": 1})
        self.assertEqual(summary["gate_comparisons"]["price_structure_gate_pass"]["not_applicable"]["N"], 1)
        self.assertEqual(summary["gate_comparisons"]["signal_direction_gate_pass"]["unavailable"]["N"], 1)


if __name__ == "__main__":
    unittest.main()
