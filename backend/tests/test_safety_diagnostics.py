"""Safety audit must observe the existing strategy, never authorize trades."""
import copy
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import test_story_outcomes as fixtures  # noqa: E402


class TestSafetyDiagnostics(unittest.TestCase):
    def setUp(self):
        self.route = fixtures.TestStoryOutcomeRoute()
        self.route.setUp()

    def test_diagnostic_mode_returns_audit_and_never_writes(self):
        response = self.route.run_route(params={"diagnostic_mode": True})
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json
        self.assertEqual(data["status"], "DIAGNOSTIC")
        self.assertEqual(data["rows_written"], 0)
        self.assertEqual(data["outcomes_generated"], 1)
        self.assertEqual(data["final_eligible_trades"], 1)
        self.assertEqual(len(data["audit_rows"]), data["story_eligible_bars"])
        self.route.cur.execute.assert_not_called()
        self.assertEqual(self.route.written, [])
        audit = data["audit_rows"][0]
        required = {
            "ts", "market_phase", "story_regime", "bar_event", "setup_key", "trade_direction",
            "regime_rule_score", "event_rule_score", "directional_edge", "regime_age_bars",
            "candidate_regime", "cost_r", "cost_gate_threshold", "cost_gate_pass", "macro_regime",
            "macro_gate_pass", "price_structure", "price_structure_gate_pass", "signal_direction_gate_pass",
            "trend_exhaustion", "trend_exhaustion_gate_pass", "final_eligible", "final_skip_reason",
        }
        self.assertTrue(required <= audit.keys())
        self.assertAlmostEqual(audit["legacy_gate_cost_r"], .15)
        self.assertAlmostEqual(audit["cost_r"], .1063343406)
        self.assertEqual(audit["cost_r"], audit["fee_cost_r_preview"])
        self.assertEqual(audit["cost_gate_threshold"], .70)
        self.assertTrue(audit["final_eligible"])
        self.assertIsNone(audit["final_skip_reason"])
        self.assertTrue(audit["ts"].endswith("Z"))

    def test_independent_overlap_does_not_reorder_first_stop(self):
        response = self.route.run_route(self.route.frame(
            macro_regime="BEAR_MACRO", price_structure="BEAR", close=99.,
            trend_exhaustion=1, atr_14=.01,
        ), params={"diagnostic_mode": True})
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json
        audit = data["audit_rows"][0]
        self.assertEqual(audit["final_skip_reason"], "MACRO_MISMATCH")
        self.assertEqual(audit["gates_reached"], ["MACRO_GATE"])
        self.assertEqual(set(audit["independent_failed_gates"]), {
            "MACRO_GATE", "PRICE_STRUCTURE_GATE", "SIGNAL_DIRECTION_GATE", "TREND_EXHAUSTION_GATE", "COST_GATE",
        })
        self.assertEqual(data["safety_pass_fail_counts"]["COST_GATE"]["failed"], 1)
        self.assertEqual(data["safety_waterfall_counts"]["COST_GATE"]["reached"], 0)
        self.assertEqual(data["cost_gate_rejection_pct_of_story_eligible"], 0)
        self.assertEqual(data["safety_pass_fail_counts"]["COST_GATE"]["failure_pct_of_story_eligible"], 100)
        self.assertEqual(data["cost_r_statistics"]["count"], 1)
        self.assertFalse(audit["final_eligible"])

    def test_empty_population_returns_null_statistics_without_deleting(self):
        frame = self.route.frame()
        frame["story_regime"] = "TRANSITION"
        response = self.route.run_route(frame, params={"diagnostic_mode": True})
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json
        self.assertEqual(data["audit_rows"], [])
        self.assertEqual(data["cost_r_statistics"]["count"], 0)
        self.assertIsNone(data["cost_r_statistics"]["p50"])
        self.assertIsNone(data["cost_gate_rejection_pct_of_story_eligible"])
        self.route.cur.execute.assert_not_called()

    def test_invalid_risk_is_unknown_not_zero_cost_or_a_pass(self):
        for atr in (0., np.nan, np.inf):
            with self.subTest(atr=atr):
                response = self.route.run_route(self.route.frame(atr_14=atr),
                                                params={"diagnostic_mode": True})
                self.assertEqual(response.status_code, 200, response.json)
                audit = response.json["audit_rows"][0]
                self.assertIsNone(audit["cost_r"])
                self.assertIsNone(audit["cost_gate_pass"])
                self.assertEqual(audit["final_skip_reason"], "INVALID_ATR")
                self.assertEqual(response.json["cost_r_statistics"]["unavailable_count"], 1)
                self.assertEqual(response.json["safety_waterfall_counts"]["COST_GATE"]["reached"], 0)

    def test_next_session_entry_is_unavailable_for_cost_statistics(self):
        frame = self.route.frame()
        frame.loc[0, "story_regime"] = "TRANSITION"
        frame.loc[11, "story_regime"] = "BULL_TREND"
        response = self.route.run_route(frame, params={"diagnostic_mode": True})
        audit = response.json["audit_rows"][0]
        self.assertIsNone(audit["cost_r"])
        self.assertEqual(audit["cost_r_unavailable_reason"], "NO_SAME_SESSION_ENTRY")
        self.assertEqual(audit["final_skip_reason"], "NEXT_BAR_OUTSIDE_SESSION")

    def test_nonapplicable_gates_are_distinguished_from_passes(self):
        response = self.route.run_route(self.route.frame(
            story_regime="GAP_AUCTION", bar_event="GAP_OPEN", market_phase="LARGE_GAP_UP",
            gap_atr=1.5, minute_of_day_mc=0,
        ), params={"diagnostic_mode": True})
        self.assertEqual(response.status_code, 200, response.json)
        row = response.json["audit_rows"][0]
        self.assertTrue(row["signal_direction_gate_pass"])
        self.assertFalse(row["signal_direction_gate_applicable"])
        self.assertEqual(response.json["safety_pass_fail_counts"]["SIGNAL_DIRECTION_GATE"]["not_applicable"], 1)
        self.assertEqual(response.json["safety_pass_fail_counts"]["SIGNAL_DIRECTION_GATE"]["passed"], 0)

    def test_normal_writes_and_diagnostic_simulation_agree(self):
        normal = self.route.run_route().json
        persisted = copy.deepcopy(self.route.written)
        self.assertEqual(len(persisted), 1)
        dry = self.route.run_route(params={"diagnostic_mode": True}).json
        self.assertEqual(dry["outcomes_generated"], normal["rows_written"])
        for key in ("eligible_trades", "skipped_by_safety", "skipped_by_eligibility",
                    "final_eligible_trades", "cost_r_statistics", "safety_waterfall_counts"):
            self.assertEqual(normal[key], dry[key])
        self.assertNotIn("audit_rows", normal)
        self.assertEqual(self.route.written, persisted)

    def test_flag_must_be_a_boolean_before_any_database_access(self):
        for value in ("true", "false", 1, [], None):
            with self.subTest(value=value), patch.object(fixtures.strategy, "get_db_conn") as db:
                response = self.route.client.post("/api/offline/calc-strategy-outcomes", json={
                    "symbol": "ITC", "timeframe": "5m", "diagnostic_mode": value,
                })
                self.assertEqual(response.status_code, 400)
                db.assert_not_called()

    def test_825_inputs_105_story_eligible_and_104_first_stop_rejections(self):
        base = self.route.frame().iloc[0].to_dict()
        dates = pd.bdate_range("2026-09-01", periods=11)
        rows = []
        for day in dates:
            for minute in range(0, 375, 5):
                value = copy.deepcopy(base)
                value.update(ts=day.tz_localize("UTC") + pd.Timedelta(hours=3, minutes=45+minute),
                             minute_of_day=minute, minute_of_day_mc=minute,
                             market_phase="TREND_CONTINUATION", story_regime="TRANSITION")
                rows.append(value)
        eligible_indices = [i for i in range(825) if i % 75 < 73][:105]
        regimes = ["BULL_TREND"]*47 + ["BEAR_TREND"]*44 + ["GAP_AUCTION"]*14
        regimes[46], regimes[103] = regimes[103], regimes[46]
        for ordinal, index in enumerate(eligible_indices):
            regime = regimes[ordinal]
            short = regime != "BULL_TREND"
            event = "GAP_OPEN" if regime == "GAP_AUCTION" else "ACCEPTANCE" if short else "CONTINUATION"
            phase = "LARGE_GAP_UP" if regime == "GAP_AUCTION" else "BEAR_TREND_CONTINUATION" if short else "TREND_CONTINUATION"
            rows[index].update(fixtures.story(
                story_regime=regime, candidate_regime=regime, bar_event=event,
                reason_details={"directional_edge": -.65 if short else .65},
            ))
            rows[index].update(market_phase=phase, close=99. if short else 101.,
                               low=98.5, price_structure="BEAR" if short else "BULL",
                               atr_14=1. if ordinal == 104 else .01)
            if 71 <= ordinal < 88:
                rows[index]["price_structure"] = "BULL" if short else "BEAR"
            elif 88 <= ordinal < 101:
                rows[index]["close"] = 101. if short else 99.
            elif 101 <= ordinal < 103:
                rows[index]["macro_regime"] = "BULL_MACRO" if short else "BEAR_MACRO"
            elif ordinal == 103:
                rows[index]["trend_exhaustion"] = 1
        response = self.route.run_route(pd.DataFrame(rows), params={"diagnostic_mode": True})
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json
        self.assertEqual(data["input_rows"], 825)
        self.assertEqual(data["story_eligible_bars"], 105)
        self.assertEqual(data["eligibility_reason_counts"]["VALID_BULL_SETUP"], 47)
        self.assertEqual(data["eligibility_reason_counts"]["VALID_BEAR_SETUP"], 44)
        self.assertEqual(data["eligibility_reason_counts"]["VALID_GAP_SETUP"], 14)
        self.assertEqual(data["final_eligible_trades"], 1)
        self.assertEqual(data["skipped_by_safety"], {
            "COST_GATE": 71, "PRICE_STRUCTURE_MISMATCH": 17,
            "SIGNAL_DIRECTION_MISMATCH": 13, "MACRO_MISMATCH": 2, "TREND_EXHAUSTED": 1,
        })
        self.assertEqual(len(data["audit_rows"]), 105)
        self.assertAlmostEqual(data["cost_gate_rejection_pct_of_story_eligible"], 100*71/105, places=5)
        self.assertEqual(data["cost_gate_rejection_fraction_of_story_eligible"], 71/105)
        self.assertEqual(data["safety_pass_fail_counts"]["COST_GATE"]["failed"], 104)
        self.assertEqual(data["safety_waterfall_counts"]["COST_GATE"]["reached"], 72)
        costs = [row["cost_r"] for row in data["audit_rows"]]
        self.assertEqual(data["cost_r_statistics"]["count"], 105)
        for percentile in (10, 25, 50, 75, 90):
            self.assertAlmostEqual(data["cost_r_statistics"][f"p{percentile}"], np.percentile(costs, percentile))
        self.assertEqual(sum(sum(v.values()) for v in data["safety_rejection_counts_by_setup_key"].values()), 104)
        self.assertEqual(sum(sum(v.values()) for v in data["safety_rejection_counts_by_direction"].values()), 104)
        self.assertEqual(data["story_eligible_counts_by_direction"], {"LONG": 47, "SHORT": 58})
        for key, stats in data["cost_r_statistics_by_setup_key"].items():
            setup_costs = [r["cost_r"] for r in data["audit_rows"] if r["setup_key"] == key]
            self.assertEqual(stats["count"], len(setup_costs))
            self.assertAlmostEqual(stats["p50"], np.percentile(setup_costs, 50))
        self.route.cur.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
