"""Fee accounting and frozen eligibility contracts for component cost V1."""
import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import test_story_outcomes as fixtures
from routes.strategy_costs import (
    COST_BREAKDOWN_FIELDS, COST_MODEL_VERSION, LEGACY_GATE_COST_PCT,
    EquityIntradayCostModel, net_r_after_fees,
)
from routes.strategy_counterfactual import _simulate_counterfactual_trade
from routes.strategy_logic import COST_R_MAX_GATE, TOTAL_COST_PCT


class TestItemizedFees(unittest.TestCase):
    def calculate(self, model=None, short=False, **changes):
        values = dict(entry_price=100., exit_price=110., risk_points=2.,
                      is_short=short, entry_slippage_pts=.05, exit_slippage_pts=.05)
        values.update(changes)
        return (model or EquityIntradayCostModel()).calculate(**values)

    def test_default_components_and_gst_base(self):
        costs = self.calculate()
        expected = dict(
            brokerage_buy_cost_pts=.03, brokerage_sell_cost_pts=.033,
            brokerage_cost_pts=.063, stt_cost_pts=.0275,
            nse_transaction_buy_cost_pts=.0030699, nse_transaction_sell_cost_pts=.00337689,
            nse_ipft_buy_cost_pts=.0000001, nse_ipft_sell_cost_pts=.00000011,
            exchange_cost_pts=.006447, sebi_buy_cost_pts=.0001,
            sebi_sell_cost_pts=.00011, sebi_cost_pts=.00021, stamp_cost_pts=.003,
        )
        for key, value in expected.items():
            self.assertAlmostEqual(costs[key], value, places=12, msg=key)
        taxable = .063 + .006447 + .00021
        self.assertAlmostEqual(costs["gst_taxable_cost_pts"], taxable)
        self.assertAlmostEqual(costs["gst_cost_pts"], .18 * taxable)
        fees = .063 + .0275 + .006447 + .00021 + .003 + .18 * taxable
        self.assertAlmostEqual(costs["total_fee_cost_pts"], fees)
        self.assertAlmostEqual(costs["fee_cost_r"], fees / 2)
        self.assertAlmostEqual(costs["slippage_r"], .05)
        self.assertAlmostEqual(costs["total_friction_r"], (fees + .1) / 2)
        self.assertEqual(costs["cost_model_version"], COST_MODEL_VERSION)
        self.assertIsNone(costs["quantity_used"])
        self.assertEqual(costs["brokerage_mode"], "PERCENTAGE")

    def test_short_uses_entry_sell_and_exit_buy_turnover(self):
        costs = self.calculate(short=True)
        self.assertAlmostEqual(costs["brokerage_buy_cost_pts"], .033)
        self.assertAlmostEqual(costs["brokerage_sell_cost_pts"], .03)
        self.assertAlmostEqual(costs["stt_cost_pts"], .025)
        self.assertAlmostEqual(costs["stamp_cost_pts"], .0033)
        self.assertAlmostEqual(costs["sebi_buy_cost_pts"], .00011)
        self.assertAlmostEqual(costs["nse_transaction_sell_cost_pts"], .0030699)

    def test_explicit_cap_per_order_only_with_known_size(self):
        percentage = self.calculate()
        no_size = self.calculate(EquityIntradayCostModel(brokerage_cap_per_order=20))
        self.assertEqual(no_size["brokerage_mode"], "PERCENTAGE_FALLBACK_NO_SIZE")
        self.assertEqual(no_size["brokerage_cost_pts"], percentage["brokerage_cost_pts"])
        self.assertFalse(no_size["brokerage_cap_applied_buy"])
        large_without_size = self.calculate(EquityIntradayCostModel(brokerage_cap_per_order=20),
                                            entry_price=100000., exit_price=110000.)
        self.assertAlmostEqual(large_without_size["brokerage_cost_pts"], 63.)
        self.assertFalse(large_without_size["brokerage_cap_applied_sell"])
        for size in ({"quantity": 1000}, {"order_notional": 100000}):
            with self.subTest(size=size):
                costs = self.calculate(EquityIntradayCostModel(brokerage_cap_per_order=20, **size))
                self.assertEqual(costs["quantity_used"], 1000)
                self.assertAlmostEqual(costs["brokerage_buy_cost_pts"], .02)
                self.assertAlmostEqual(costs["brokerage_sell_cost_pts"], .02)
                self.assertEqual(costs["brokerage_mode"], "CAPPED_PER_ORDER")
                self.assertTrue(costs["brokerage_cap_applied_buy"])
                self.assertTrue(costs["brokerage_cap_applied_sell"])
                # Cap changes brokerage and its GST only, not the other charges.
                self.assertAlmostEqual(percentage["total_fee_cost_pts"] - costs["total_fee_cost_pts"],
                                       (.063 - .04) * 1.18)
        small = self.calculate(EquityIntradayCostModel(quantity=10, brokerage_cap_per_order=20))
        self.assertEqual(small["brokerage_cost_pts"], percentage["brokerage_cost_pts"])
        # A cap is never assumed just because quantity is known.
        uncapped = self.calculate(EquityIntradayCostModel(quantity=1000))
        self.assertEqual(uncapped["brokerage_cost_pts"], percentage["brokerage_cost_pts"])

    def test_cap_is_separate_for_each_side_and_supports_zero_brokerage(self):
        costs = self.calculate(EquityIntradayCostModel(quantity=100, brokerage_cap_per_order=3.1))
        self.assertAlmostEqual(costs["brokerage_buy_cost_pts"], .03)
        self.assertAlmostEqual(costs["brokerage_sell_cost_pts"], .031)
        self.assertFalse(costs["brokerage_cap_applied_buy"])
        self.assertTrue(costs["brokerage_cap_applied_sell"])
        costs = self.calculate(EquityIntradayCostModel(brokerage_rate=0))
        self.assertEqual(costs["brokerage_cost_pts"], 0)
        self.assertGreater(costs["gst_cost_pts"], 0)  # exchange + SEBI still taxable

    def test_slippage_is_never_a_percentage_fee_or_deducted_twice(self):
        costs = self.calculate()
        changed = self.calculate(entry_slippage_pts=5., exit_slippage_pts=3.)
        for key in COST_BREAKDOWN_FIELDS:
            if key not in ("entry_slippage_pts", "exit_slippage_pts", "total_friction_pts", "slippage_r", "total_friction_r"):
                self.assertEqual(costs[key], changed[key], key)
        self.assertEqual(net_r_after_fees(1.5, costs), 1.5 - costs["fee_cost_r"])
        self.assertEqual(net_r_after_fees(1.5, costs), net_r_after_fees(1.5, changed))
        self.assertNotEqual(net_r_after_fees(1.5, costs), 1.5 - costs["total_friction_r"])
        broken = dict(costs, total_fee_cost_pts=costs["total_fee_cost_pts"] + .1)
        with self.assertRaises(AssertionError):
            net_r_after_fees(1.5, broken)

    def test_invalid_request_config_is_rejected(self):
        for options in (None, [], True, {"brokerage_rate": -1}, {"gst_rate": 18},
                        {"quantity": 0}, {"quantity": True}, {"order_notional": float("inf")},
                        {"brokerage_rate": "0.0003"}, {"brokerage_rate": None},
                        {"brokerage_cap_per_order": -20}, {"quantity": 10, "order_notional": 1000},
                        {"brokerage_cap": 20}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                EquityIntradayCostModel.from_request(options)


class TestCostRouteAndResearch(unittest.TestCase):
    def setUp(self):
        self.route = fixtures.TestStoryOutcomeRoute()
        self.route.setUp()

    def test_normal_diagnostic_and_counterfactual_fee_parity(self):
        for options in ({}, {"brokerage_rate": .0002, "brokerage_cap_per_order": 20, "quantity": 10000},
                        {"brokerage_cap_per_order": 20, "order_notional": 100000}):
            with self.subTest(options=options):
                self.route.written = []
                normal = self.route.run_route(params={"cost_model": options}).json
                stored = self.route.written[0]
                diagnostic = self.route.run_route(params={"diagnostic_mode": True, "cost_model": options}).json
                research = self.route.run_route(params={"counterfactual_mode": True, "cost_model": options}).json
                audit = diagnostic["audit_rows"][0]
                cf = research["counterfactual_rows"][0]
                for key in COST_BREAKDOWN_FIELDS:
                    self.assertEqual(audit[key], cf[key], key)
                self.assertEqual(stored["cost_r"], cf["fee_cost_r"])
                self.assertEqual(stored["realized_r"], cf["realized_r_net"])
                self.assertEqual(stored["realized_r_gross"], cf["realized_r_gross"])
                self.assertEqual(cf["realized_r_net"], cf["realized_r_gross"] - cf["fee_cost_r"])
                self.assertEqual(normal["cost_model_version"], COST_MODEL_VERSION)
                self.assertEqual(cf["cost_r"], cf["fee_cost_r"])
                self.assertAlmostEqual(audit["cost_r"], .15)  # still legacy gate preview
                self.assertAlmostEqual(cf["gate_cost_r"], .15)
                self.assertEqual(research["rows_written"], 0)
                self.assertEqual(len(self.route.written), 1)
                self.assertEqual(cf["fee_breakdown_status"], "CALCULATED")

    def test_brokerage_changes_net_only_never_eligibility_gross_or_excursions(self):
        self.assertEqual(COST_R_MAX_GATE, .70)
        self.assertEqual(TOTAL_COST_PCT, .00150)
        self.assertEqual(LEGACY_GATE_COST_PCT, .00150)
        for atr in (.1, 1.):
            responses = []
            for model in ({"brokerage_rate": 0}, {"brokerage_rate": .01, "brokerage_cap_per_order": 20}):
                responses.append(self.route.run_route(self.route.frame(atr_14=atr), {
                    "counterfactual_mode": True, "cost_model": model,
                }).json)
            low, high = (r["counterfactual_rows"][0] for r in responses)
            self.assertGreater(low["realized_r_net"], high["realized_r_net"])
            for key in ("production_eligible", "production_skip_reason", "independent_failed_gates",
                        "cost_gate_pass", "cost_r_gate", "gate_cost_r", "exit_reason", "exit_ts",
                        "exit_after_candles", "entry_price", "risk_points", "realized_r_gross",
                        "trade_mfe_r", "trade_mae_r", "horizon_mfe_r", "horizon_mae_r"):
                self.assertEqual(low[key], high[key], key)
            self.assertEqual(responses[0]["skipped_by_safety"], responses[1]["skipped_by_safety"])
            self.assertEqual(low["production_eligible"], atr == 1.)

    def test_tp_sl_and_time_gross_slippage_contract_both_directions(self):
        import pandas as pd
        for short in (False, True):
            for reason, hi, lo, close in (
                ("TP_HIT", 100.5 if short else 102., 98. if short else 99.5, 100.),
                ("SL_HIT", 102., 98., 100.),
                ("TIME_EXIT", 100.2, 99.8, 100.1),
            ):
                with self.subTest(short=short, reason=reason):
                    row = _simulate_counterfactual_trade(
                        raw_entry=100., atr=1., cfg={"tp": 1., "sl": 1.},
                        highs=np.array([hi]), lows=np.array([lo]), closes=np.array([close]),
                        timestamps=[pd.Timestamp("2026-10-16T04:05Z")], horizon_n=1, is_short=short,
                    )
                    self.assertEqual(row["exit_reason"], reason)
                    self.assertAlmostEqual(row["entry_slippage_pts"], .05)
                    self.assertAlmostEqual(row["exit_slippage_pts"], .05 if reason == "TP_HIT" else 0)
                    expected_gross = .95 if reason == "TP_HIT" else -1 if reason == "SL_HIT" else -.15 if short else .05
                    self.assertAlmostEqual(row["realized_r_gross"], expected_gross)
                    self.assertEqual(row["realized_r_net"], row["realized_r_gross"] - row["fee_cost_r"])
                    self.assertAlmostEqual(row["total_friction_r"], row["fee_cost_r"] + row["slippage_r"])

    def test_both_cost_measures_bucket_independently_and_report_cost_distributions(self):
        # Fees ~.62R and slippage ~.59R -> distinct fee/friction bins.
        frame = self.route.frame(atr_14=.17)
        frame.loc[1, "low"] = 100.  # hit TP alone, so the modeled exit tick applies
        data = self.route.run_route(frame, {"counterfactual_mode": True}).json
        row = data["counterfactual_rows"][0]
        summary = data["counterfactual_summary"]
        self.assertEqual(summary["fee_cost_r_buckets"]["<=0.70"]["N"], 1)
        self.assertEqual(summary["total_friction_r_buckets"]["(1.00,1.25]"]["N"], 1)
        self.assertEqual(summary["cost_buckets"], summary["fee_cost_r_buckets"])
        for metric in ("fee_cost_r", "slippage_r", "total_friction_r"):
            for key in ("mean", "p10", "p25", "p50", "p75", "p90"):
                self.assertEqual(summary["overall"][metric][key], row[metric])
        self.route.cur.execute.assert_not_called()

    def test_diagnostic_rejected_rows_have_unknown_exit_fees_not_fake_estimates(self):
        data = self.route.run_route(self.route.frame(atr_14=.1), {"diagnostic_mode": True}).json
        row = data["audit_rows"][0]
        self.assertEqual(row["final_skip_reason"], "COST_GATE")
        self.assertEqual(row["fee_breakdown_status"], "NOT_SIMULATED")
        self.assertEqual(row["cost_model_version"], COST_MODEL_VERSION)
        for key in COST_BREAKDOWN_FIELDS:
            self.assertIsNone(row[key], key)
        self.assertGreater(row["cost_r"], .7)

    def test_bad_cost_config_does_not_touch_database_or_calibration(self):
        for options in ({"quantity": -1}, {"gst_rate": 18}, None):
            with self.subTest(options=options), patch.object(fixtures.strategy, "get_db_conn") as db, \
                 patch.object(fixtures.strategy, "calibrate_phase_params") as calibrate:
                response = self.route.client.post("/api/offline/calc-strategy-outcomes", json={
                    "symbol": "ITC", "timeframe": "5m", "cost_model": options,
                })
                self.assertEqual(response.status_code, 400)
                db.assert_not_called()
                calibrate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
