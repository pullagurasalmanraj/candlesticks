"""COST_GATE uses componentized pre-entry estimates, never legacy or realized fees."""
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import test_story_outcomes as fixtures
from routes.strategy_costs import EquityIntradayCostModel, pretrade_cost_gate_preview
from routes.strategy_diagnostics import SafetyWaterfallAudit


class TestComponentCostGate(unittest.TestCase):
    def setUp(self):
        self.route = fixtures.TestStoryOutcomeRoute()
        self.route.setUp()

    def test_reported_legacy_rejections_now_pass_component_preview(self):
        for legacy_cost in (.9034167541, .9143181818):
            for short in (False, True):
                with self.subTest(legacy_cost=legacy_cost, short=short):
                    frame = self.route.frame(atr_14=.15/legacy_cost)
                    if short:
                        frame.loc[0, ["story_regime", "candidate_regime", "market_phase", "price_structure", "close"]] = [
                            "BEAR_TREND", "BEAR_TREND", "TREND_ACCEPTANCE", "BEAR", 99.]
                        frame.at[0, "reason_details"] = {"directional_edge": -.65}
                    normal = self.route.run_route(frame)
                    self.assertEqual(normal.status_code, 200, normal.json)
                    diagnostic = self.route.run_route(frame, {"diagnostic_mode": True}).json["audit_rows"][0]
                    data = self.route.run_route(frame, {"counterfactual_mode": True}).json
                    row = data["counterfactual_rows"][0]
                    self.assertAlmostEqual(row["legacy_gate_cost_r"], legacy_cost)
                    self.assertLess(row["fee_cost_r_preview"], .70)
                    self.assertEqual(row["cost_gate_threshold"], .70)
                    self.assertEqual(row["cost_gate_metric"], row["fee_cost_r_preview"])
                    self.assertEqual(row["gate_cost_r"], row["cost_gate_metric"])
                    self.assertTrue(row["cost_gate_pass"])
                    self.assertTrue(row["production_eligible"])
                    self.assertIsNone(row["production_skip_reason"])
                    self.assertNotIn("COST_GATE", row["independent_failed_gates"])
                    self.assertEqual(diagnostic["cost_gate_metric"], row["cost_gate_metric"])
                    self.assertEqual(diagnostic["cost_r"], row["cost_gate_metric"])
                    self.assertEqual(data["skipped_by_cost"], 0)
                    self.assertEqual(data["cost_gate_exit_price_basis"], "FLAT_EXIT_AT_ENTRY")

    def test_realized_exit_can_cross_threshold_without_changing_gate(self):
        # Entry 100.05 and a flat exit cost 0.1063343406 pts with default fees.
        # Preview just below 0.70; actual TP exit is dearer and crosses 0.70.
        frame = self.route.frame(atr_14=.1063343406/.6998)
        frame.loc[1, ["high", "low", "close"]] = [102., 100., 101.]
        tp = self.route.run_route(frame, {"counterfactual_mode": True}).json["counterfactual_rows"][0]
        frame.loc[1, ["high", "low", "close"]] = [100.1, 98., 99.]
        sl = self.route.run_route(frame, {"counterfactual_mode": True}).json["counterfactual_rows"][0]
        self.assertEqual(tp["exit_reason"], "TP_HIT")
        self.assertEqual(sl["exit_reason"], "SL_HIT")
        self.assertGreater(tp["fee_cost_r"], .70)
        self.assertLess(sl["fee_cost_r"], .70)
        self.assertNotEqual(tp["realized_r_net"], sl["realized_r_net"])
        self.assertAlmostEqual(tp["cost_gate_metric"], .6998)
        for key in ("cost_gate_metric", "fee_cost_r_preview", "legacy_gate_cost_r", "cost_gate_pass",
                    "production_eligible", "production_skip_reason", "independent_failed_gates",
                    "macro_gate_pass", "price_structure_gate_pass", "trend_exhaustion_gate_pass",
                    "signal_direction_gate_pass"):
            self.assertEqual(tp[key], sl[key], key)
        self.assertTrue(tp["production_eligible"])
        self.assertTrue(tp["cost_gate_pass"])
        self.assertEqual(tp["realized_r_net"], tp["realized_r_gross"] - tp["fee_cost_r"])
        self.assertAlmostEqual(tp["total_friction_r"], tp["fee_cost_r"] + tp["slippage_r"])
        self.route.cur.execute.assert_not_called()

    def test_threshold_equality_passes_and_only_strict_excess_rejects(self):
        metric = self.route.run_route(params={"diagnostic_mode": True}).json["audit_rows"][0]["cost_gate_metric"]
        # Exercise the existing per-request threshold at adjacent floating-point
        # values; the actual default COST_R_MAX_GATE is not changed by this test.
        for threshold, expected in ((metric, True), (np.nextafter(metric, np.inf), True),
                                    (np.nextafter(metric, -np.inf), False)):
            with self.subTest(threshold=threshold):
                row = self.route.run_route(params={
                    "counterfactual_mode": True, "cost_r_gate": float(threshold),
                }).json["counterfactual_rows"][0]
                self.assertEqual(row["cost_gate_pass"], expected)
                self.assertEqual(row["production_eligible"], expected)
                self.assertEqual(row["production_skip_reason"], None if expected else "COST_GATE")
                if row["cost_gate_metric"] <= row["cost_gate_threshold"]:
                    self.assertNotEqual(row["production_skip_reason"], "COST_GATE")

    def test_broker_caps_and_percentage_fallback_feed_gate(self):
        frame = self.route.frame(atr_14=.12)
        rows = []
        for config in ({}, {"brokerage_cap_per_order": 20},
                       {"brokerage_cap_per_order": 20, "quantity": 10000},
                       {"brokerage_cap_per_order": 20, "order_notional": 1000500}):
            rows.append(self.route.run_route(frame, {
                "counterfactual_mode": True, "cost_model": config,
            }).json["counterfactual_rows"][0])
        self.assertEqual([row["cost_gate_pass"] for row in rows], [False, False, True, True])
        self.assertEqual(rows[0]["cost_gate_metric"], rows[1]["cost_gate_metric"])
        self.assertEqual(rows[1]["brokerage_mode_preview"], "PERCENTAGE_FALLBACK_NO_SIZE")
        self.assertEqual(rows[2]["cost_gate_metric"], rows[3]["cost_gate_metric"])
        self.assertEqual(rows[2]["brokerage_mode_preview"], "CAPPED_PER_ORDER")
        for row in rows:
            self.assertEqual(row["cost_gate_threshold"], .70)
            self.assertEqual(row["legacy_gate_cost_r"], rows[0]["legacy_gate_cost_r"])

    def test_estimate_is_flat_execution_turnover_not_planned_barrier_or_future_price(self):
        model = EquityIntradayCostModel(brokerage_cap_per_order=20, order_notional=100000.)
        for short in (False, True):
            values = dict(cost_model=model, cfg={"sl": 2., "tp": 1., "lookahead_min": 15}, atr=.5,
                          raw_entry=100., same_session=True, is_short=short,
                          entry_slippage_pts=.05, threshold=.70)
            preview = pretrade_cost_gate_preview(**values)
            values["cfg"] = {"sl": 2., "tp": 100., "lookahead_min": 375}
            self.assertEqual(preview, pretrade_cost_gate_preview(**values))
            entry = 99.95 if short else 100.05
            costs = model.calculate(entry_price=entry, exit_price=entry, risk_points=1.,
                                    is_short=short, entry_slippage_pts=.05, exit_slippage_pts=0.)
            self.assertEqual(preview["cost_gate_estimated_entry_price"], entry)
            self.assertEqual(preview["cost_gate_estimated_exit_price"], entry)
            self.assertEqual(preview["cost_gate_metric"], costs["fee_cost_r"])
            self.assertNotEqual(preview["cost_gate_metric"], costs["total_friction_r"])

    def test_missing_data_never_falls_back_to_legacy_gate_or_zero(self):
        for changes, reason in (({"atr": 0}, "INVALID_ATR"), ({"same_session": False}, "NO_SAME_SESSION_ENTRY"),
                                ({"cfg": None}, "MISSING_PHASE_CONFIG"),
                                ({"raw_entry": .04, "is_short": True}, "INVALID_ENTRY")):
            preview = pretrade_cost_gate_preview(**{
                "cost_model": EquityIntradayCostModel(), "cfg": {"sl": 1.}, "atr": 1.,
                "raw_entry": 100., "same_session": True, "is_short": False,
                "entry_slippage_pts": .05, "threshold": .70, **changes,
            })
            self.assertIsNone(preview["cost_gate_metric"])
            self.assertIsNone(preview["fee_cost_r_preview"])
            self.assertIsNone(preview["cost_gate_pass"])
            self.assertEqual(preview["cost_r_unavailable_reason"], reason)

    def test_runtime_sanity_guard_rejects_inconsistent_cost_rejection(self):
        row = self.route.run_route(params={"diagnostic_mode": True}).json["audit_rows"][0]
        row.update(final_eligible=False, final_skip_reason=None)
        self.assertLessEqual(row["cost_gate_metric"], row["cost_gate_threshold"])
        with self.assertRaisesRegex(AssertionError, "passing fee preview"):
            SafetyWaterfallAudit().finish(row, "COST_GATE")

    def test_nonfinite_threshold_cannot_produce_an_unknown_or_inconsistent_pass(self):
        for threshold in (None, "NaN", "Infinity", "not a number"):
            with self.subTest(threshold=threshold), patch.object(fixtures.strategy, "get_db_conn") as db:
                response = self.route.client.post("/api/offline/calc-strategy-outcomes", json={
                    "symbol": "ITC", "timeframe": "5m", "cost_r_gate": threshold,
                })
                self.assertEqual(response.status_code, 400)
                db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
