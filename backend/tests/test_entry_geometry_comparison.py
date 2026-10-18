"""Causal, response-only entry/geometry comparisons with a sealed holdout."""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import test_story_outcomes as fixtures
from routes import strategy_comparison as research
from routes.strategy_costs import EquityIntradayCostModel
from routes.strategy_logic import PHASE_MODEL


def history(days=4, signals=(0,)):
    template = fixtures.TestStoryOutcomeRoute()
    template.setUp()
    source = template.frame().iloc[:12]
    frames = []
    for day in range(days):
        frame = source.copy(deep=True)
        frame["ts"] = pd.date_range(pd.Timestamp("2026-09-01T04:00Z") + pd.Timedelta(days=day), periods=12, freq="5min")
        frame["story_regime"] = "TRANSITION"
        frame.loc[list(signals), "story_regime"] = "BULL_TREND"
        frame["symbol"] = "ITC"
        frame["volume"] = 1000
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def compare(frame, **options):
    return research.compare_symbol(frame, split_at=pd.Timestamp("2026-09-03T00:00", tz="Asia/Kolkata").tz_convert("UTC"),
                                   from_dt=pd.Timestamp("2026-08-31T18:30Z"), params=options.get("params", {}),
                                   cost_model=options.get("cost_model", EquityIntradayCostModel()))


class TestComparisonEngine(unittest.TestCase):
    def test_baseline_matches_existing_production_simulator(self):
        template = fixtures.TestStoryOutcomeRoute()
        template.setUp()
        template.run_route(history(1).drop(columns=["symbol", "volume"]))
        production = template.written[0]
        result = compare(history())
        baseline = result["periods"]["research"]["variants"]["baseline"]["raw_signals"]
        self.assertEqual(baseline["samples"], 2)
        self.assertEqual(baseline["tp_pct"], 100)
        self.assertEqual(baseline["sl_pct"], 0)
        for metric in ("realized_r_gross", "trade_mfe", "trade_mae", "trade_mfe_r", "trade_mae_r"):
            self.assertEqual(baseline[metric]["avg"], production[metric])
        self.assertEqual(baseline["realized_r_net"]["avg"], production["realized_r"])
        self.assertEqual(baseline["net_points"]["avg"], production["realized_r"])

    def test_timing_is_exact_bar_delay_and_atr_story_are_frozen(self):
        frame = history()
        frame.loc[0, "atr_14"] = 2.
        frame.loc[[1, 2, 3], "open"] = [101., 102., 103.]
        frame.loc[1:11, "atr_14"] = 100.
        with patch.object(research, "_simulate_counterfactual_trade", wraps=research._simulate_counterfactual_trade) as simulator:
            result = compare(frame)
        # Two research signals per variant; first signal call supplies the prices.
        first = [simulator.call_args_list[i*2].kwargs for i in range(len(research.VARIANTS))]
        self.assertEqual([call["raw_entry"] for call in first[:3]], [101., 102., 103.])
        self.assertTrue(all(call["atr"] == 2. for call in first))
        self.assertTrue(all(call["raw_entry"] == 101. for call in first[3:]))
        self.assertEqual([call["horizon_n"] for call in first], [9]*7)
        cfg = PHASE_MODEL["BEAR_TREND_ACCEPTANCE"]
        for call, variant in zip(first, research.VARIANTS):
            self.assertEqual(call["cfg"]["tp"], cfg["tp"]*variant.tp_scale)
            self.assertEqual(call["cfg"]["sl"], cfg["sl"]*variant.sl_scale)
            self.assertFalse(call["is_short"])
        self.assertEqual(result["periods"]["research"]["story_eligible_signals"], 2)

    def test_holdout_outcomes_cannot_change_research_results_or_fixed_variants(self):
        frame = history(signals=(0, 2, 8))
        original = compare(frame)
        frame.loc[24:, ["high", "low", "close"]] = [150., 50., 75.]
        changed = compare(frame)
        self.assertEqual(original["periods"]["research"], changed["periods"]["research"])
        self.assertEqual(original["baseline_parameters"], changed["baseline_parameters"])
        self.assertNotEqual(original["periods"]["holdout"], changed["periods"]["holdout"])
        self.assertEqual([v.name for v in research.VARIANTS],
                         ["baseline", "delay_1", "delay_2", "tp_0_8x", "tp_1_2x", "sl_0_8x", "sl_1_2x"])

    def test_session_end_misses_do_not_leak_into_next_session_or_holdout(self):
        result = compare(history(signals=(9, 11)))
        for period in result["periods"].values():
            variants = period["variants"]
            self.assertEqual(period["story_eligible_signals"], 4)
            self.assertEqual(variants["baseline"]["raw_signals"]["missed_entry_count"], 2)
            self.assertEqual(variants["delay_1"]["raw_signals"]["missed_entry_count"], 2)
            self.assertEqual(variants["delay_2"]["raw_signals"]["missed_entry_count"], 4)
            for variant in variants.values():
                for model in ("raw_signals", "non_overlapping"):
                    stats = variant[model]
                    self.assertEqual(stats["samples"] + stats["missed_entry_count"] +
                                     stats["unavailable_outcome_count"] + stats["overlap_skipped_count"], 4)

    def test_pending_orders_and_positions_reserve_slot_without_choosing_winners(self):
        rows = [
            {"signal_index": 0, "entry_index": 3, "exit_index": 5, "release_index": 5, "status": "SIMULATED"},
            {"signal_index": 1, "entry_index": 4, "exit_index": 4, "release_index": 4, "status": "SIMULATED"},
            {"signal_index": 4, "entry_index": 7, "exit_index": 8, "release_index": 8, "status": "SIMULATED"},
            {"signal_index": 5, "entry_index": 8, "exit_index": 9, "release_index": 9, "status": "SIMULATED"},
        ]
        selected, notes = research._non_overlapping(rows)
        self.assertEqual([r["overlap_skipped"] for r in selected], [False, True, True, False])
        self.assertEqual(notes["pending_order_skips"], 1)
        flags = research._overlap_flags(rows)
        self.assertEqual(flags["overlapping_trade_count"], 4)
        self.assertEqual(flags["max_concurrent_trades"], 2)
        # Unknown future outcome must not let us replace the first pending order.
        rows[0].update(status="OUTCOME_UNAVAILABLE", release_index=11)
        selected, _ = research._non_overlapping(rows)
        self.assertEqual([r["overlap_skipped"] for r in selected], [False, True, True, True])

    def test_overlap_and_setup_breakdowns_reconcile_and_are_distinct_from_raw(self):
        frame = history(signals=(0, 1, 2, 3))
        frame[["high", "low", "close"]] = [100.3, 99.8, 100.1]
        frame.loc[frame.index % 12 == 8, "high"] = 102.
        result = compare(frame)
        variants = result["periods"]["research"]["variants"]
        self.assertGreater(variants["delay_2"]["non_overlapping"]["pending_order_skips"], 0)
        for variant in variants.values():
            for model in ("raw_signals", "non_overlapping"):
                stats = variant[model]
                self.assertEqual(sum(s["samples"] for s in stats["by_setup_key"].values()), stats["samples"])
                self.assertEqual(stats["story_signal_count"], 8)
            self.assertEqual(variant["raw_signals"]["overlap_skipped_count"], 0)
        self.assertLess(variants["delay_2"]["non_overlapping"]["samples"], variants["delay_2"]["raw_signals"]["samples"])
        self.assertGreater(variants["baseline"]["overlap_flags"]["overlapping_trade_count"], 0)

    def test_calibration_is_frozen_and_overlap_or_unknown_dates_cannot_leak(self):
        phase = "BEAR_TREND_ACCEPTANCE"
        candidate = {"tp": 1.4, "sl": .7, "lookahead_min": 20, "viable": True,
                     "calibrated_to": "2026-09-03T00:00Z"}
        original = compare(history())
        leaking = compare(history(), params={phase: candidate})
        self.assertEqual(original["baseline_parameters"], leaking["baseline_parameters"])
        self.assertTrue(leaking["parameter_provenance"]["overlapping_calibration_ignored"])
        candidate["calibrated_to"] = "2026-08-20T00:00Z"
        fitted = compare(history(), params={phase: candidate})
        self.assertEqual(fitted["baseline_parameters"][phase]["source"], "calibrated")
        self.assertEqual(fitted["baseline_parameters"][phase]["lookahead_bars"], 4)
        candidate["calibrated_to"] = None
        unknown = compare(history(), params={phase: candidate})
        self.assertEqual(original["baseline_parameters"], unknown["baseline_parameters"])

    def test_missing_story_candle_still_supplies_an_entry_and_short_uses_story_direction(self):
        frame = history()
        frame.loc[frame.index % 12 == 0, ["story_regime", "candidate_regime", "market_phase"]] = [
            "BEAR_TREND", "BEAR_TREND", "TREND_ACCEPTANCE"]
        for i in frame.index[frame.index % 12 == 0]:
            frame.at[i, "reason_details"] = {"directional_edge": -.65}
        frame.loc[frame.index % 12 == 1, "story_regime"] = None
        frame.loc[1, "open"] = 103.
        with patch.object(research, "_simulate_counterfactual_trade", wraps=research._simulate_counterfactual_trade) as simulator:
            result = compare(frame)
        self.assertTrue(simulator.call_args_list[0].kwargs["is_short"])
        self.assertEqual(simulator.call_args_list[0].kwargs["raw_entry"], 103.)
        self.assertEqual(result["data_quality"]["bars_without_story_labels"], 4)

    def test_invalid_inputs_are_counted_and_unavailable_outcomes_are_not_missed_entries(self):
        frame = history()
        frame.loc[0, "atr_14"] = 0.
        frame.loc[13, "high"] = np.nan
        result = compare(frame)["periods"]["research"]["variants"]["baseline"]["raw_signals"]
        self.assertEqual(result["samples"], 0)
        self.assertEqual(result["missed_entry_reasons"], {"INVALID_SIGNAL_ATR": 1})
        self.assertEqual(result["unavailable_outcome_reasons"], {"INVALID_FUTURE_PRICES": 1})
        self.assertIsNone(result["realized_r_net"]["avg"])
        self.assertIsNone(result["tp_pct"])
        frame = history()
        frame.loc[1, "ts"] = frame.loc[0, "ts"]
        with self.assertRaisesRegex(ValueError, "unique"):
            compare(frame)

    def test_missing_story_labels_cannot_be_reported_as_a_successful_comparison(self):
        frame = history()
        frame["story_regime"] = None
        result = compare(frame)
        self.assertEqual(result["status"], "NO_STORY_ELIGIBLE_SIGNALS")
        self.assertEqual(result["eligibility_reason_counts"], {"MISSING_STORY_CONTEXT": 48})
        self.assertEqual(result["periods"]["research"]["story_eligible_signals"], 0)

    def test_compactness_does_not_scale_with_signal_audit_row_count(self):
        small = compare(history(4, signals=tuple(range(10))))
        large = compare(history(24, signals=tuple(range(10))))
        small_size, large_size = len(json.dumps(small)), len(json.dumps(large))
        self.assertLess(large_size, small_size*1.15)
        self.assertLess(large_size, 200000)
        self.assertNotIn('"audit_rows"', json.dumps(large))


class TestComparisonEndpoint(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(research.comparison_bp)
        self.client = app.test_client()
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.schema = pd.DataFrame([{"table_name": "market_context", "column_name": key} for key in fixtures.strategy.STORY_INPUT_COLUMNS])

    def run_route(self, frame=None, data=None, schema=None):
        frame = frame if frame is not None else history()
        combined = pd.concat([frame, frame.assign(symbol="TATASTEEL")], ignore_index=True)
        self.conn.info.host = "unit-postgres"
        self.conn.info.port = 5432
        cursor = self.conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "database": "unit_db", "schema": "public", "search_path": '"$user", public',
            "transaction_read_only": "on", "transaction_isolation": "repeatable read",
            "server_address": "127.0.0.1/32", "server_port": 5432,
        }
        cursor.fetchall.return_value = [{"symbol": s, "indicator_rows": len(g),
            "matching_context_rows": int(g.story_regime.notna().sum()),
            "nonnull_story_regime": int(g.story_regime.notna().sum())}
            for s, g in combined.groupby("symbol")]
        with patch.object(research, "get_db_conn", return_value=self.conn), \
             patch.object(research, "read_sql_safe", side_effect=[self.schema if schema is None else schema, combined]) as read:
            response = self.client.post("/api/offline/compare-entry-geometry", json=data or {})
            self.queries = read.call_args_list
        return response

    def test_read_only_snapshot_shared_date_split_and_no_writers(self):
        response = self.run_route()
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json
        self.assertTrue(data["research_only"])
        self.assertFalse(data["holdout_used_for_selection"])
        self.assertFalse(data["parameter_selection_performed"])
        self.assertEqual(data["rows_written"], 0)
        self.assertEqual(set(data["symbols"]), {"ITC", "TATASTEEL"})
        for result in data["symbols"].values():
            self.assertEqual(result["periods"]["research"]["input_rows"], 24)
            self.assertEqual(result["periods"]["holdout"]["input_rows"], 24)
        self.assertEqual(data["split"]["research_to_exclusive"], data["split"]["holdout_from_inclusive"])
        self.conn.set_session.assert_called_once_with(readonly=True, isolation_level="REPEATABLE READ")
        self.conn.close.assert_called_once()
        self.conn.cursor.assert_called_once()  # independent counts use the same connection
        raw_calls = self.conn.cursor.return_value.__enter__.return_value.execute.call_args_list
        self.assertTrue(all(q.args[0].lstrip().startswith("SELECT") for q in raw_calls))
        self.assertEqual(raw_calls[1].args[1], self.queries[1].kwargs["params"])
        diagnostics = data["data_read_diagnostics"]
        self.assertEqual(diagnostics["connection"]["host"], "unit-postgres")
        self.assertEqual(diagnostics["stage_by_symbol"], {"ITC": "CONSISTENT", "TATASTEEL": "CONSISTENT"})
        self.assertEqual(diagnostics["sql_counts"]["ITC"]["nonnull_story_regime"], 48)
        self.assertEqual(diagnostics["after_read_sql_safe"]["ITC"]["nonnull_story_regime"], 48)
        self.assertTrue(all(q.args[0].lstrip().startswith("SELECT") for q in self.queries))
        self.assertIn("LEFT JOIN market_context", self.queries[1].args[0])
        self.assertNotIn("strategy_outcomes", self.queries[1].args[0])
        self.assertEqual(self.queries[1].kwargs["params"][0], ["ITC", "TATASTEEL"])

    def test_explicit_split_and_invalid_requests_before_database_access(self):
        data = self.run_route(data={"holdout_from_date": "2026-09-04"}).json
        self.assertEqual(data["symbols"]["ITC"]["periods"]["research"]["input_rows"], 36)
        for invalid in ({"variants": []}, {"story_policy": {}}, {"timeframe": "1m"},
                        {"symbols": ["ITC"]}, {"from_date": "invalid"},
                        {"holdout_from_date": "2026-09-03T00:00Z"},
                        {"from_date": "2026-09-01", "to_date": "2026-09-04", "holdout_from_date": "2026-08-30"}):
            with self.subTest(invalid=invalid), patch.object(research, "get_db_conn") as db:
                response = self.client.post("/api/offline/compare-entry-geometry", json=invalid)
                self.assertEqual(response.status_code, 400)
                db.assert_not_called()

    def test_missing_data_or_schema_are_explicit_and_connection_always_closes(self):
        response = self.run_route(frame=pd.DataFrame(columns=history().columns))
        self.assertEqual(response.json["status"], "NO_DATA")
        response = self.run_route(frame=history(1))
        self.assertEqual(response.json["status"], "INSUFFICIENT_SPLIT_DATA")
        schema = self.schema.loc[self.schema.column_name != "story_regime"]
        # Missing schema stops before the historical price read.
        with patch.object(research, "get_db_conn", return_value=self.conn), \
             patch.object(research, "read_sql_safe", return_value=schema):
            response = self.client.post("/api/offline/compare-entry-geometry", json={})
        self.assertEqual(response.status_code, 409)
        self.assertIn("story_regime", response.json["missing_columns"])

    def test_database_errors_return_compact_json_without_sensitive_details(self):
        with patch.object(research, "get_db_conn", side_effect=research.DatabaseError("private connection details")):
            response = self.client.post("/api/offline/compare-entry-geometry", json={})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["rows_written"], 0)
        self.assertNotIn("private", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
