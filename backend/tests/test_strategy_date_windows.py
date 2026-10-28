"""IST day boundaries must match across research reads, cleanup and calibration."""
import copy
import os
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import test_story_outcomes as fixtures  # noqa: E402
from routes.strategy_dates import _research_date_window  # noqa: E402


class TestResearchDateWindow(unittest.TestCase):
    def test_complete_nov20_through_dec10_ist_days(self):
        start, end = _research_date_window("2025-11-20", "2025-12-10")
        self.assertEqual(start, pd.Timestamp("2025-11-19T18:30:00Z"))
        self.assertEqual(end, pd.Timestamp("2025-12-10T18:30:00Z"))
        for instant in (start, pd.Timestamp("2025-12-10T03:45:00Z"),
                        end - pd.Timedelta(microseconds=1)):
            self.assertTrue(start <= instant < end)
        self.assertFalse(start <= end < end)

    def test_same_day_and_leap_day_are_full_days(self):
        for day, next_day in (("2025-12-10", "2025-12-11"),
                              ("2024-02-29", "2024-03-01"),
                              ("2025-12-31", "2026-01-01")):
            with self.subTest(day=day):
                start, end = _research_date_window(day, day)
                self.assertEqual(end - start, pd.Timedelta(days=1))
                self.assertEqual(end.tz_convert("Asia/Kolkata").strftime("%Y-%m-%d %H:%M"),
                                 next_day + " 00:00")

    def test_explicit_timestamp_keeps_instant_and_exclusive_end(self):
        start, end = _research_date_window("2025-12-10T09:15:00+05:30",
                                            "2025-12-10T10:00:00+05:30")
        self.assertEqual(start, pd.Timestamp("2025-12-10T03:45:00Z"))
        self.assertEqual(end, pd.Timestamp("2025-12-10T04:30:00Z"))
        _, naive_end = _research_date_window("2025-12-10", "2025-12-10T04:30:00")
        self.assertEqual(end, naive_end)
        _, utc_end = _research_date_window("2025-12-10", "2025-12-10T00:00:00Z")
        self.assertEqual(utc_end, pd.Timestamp("2025-12-10T00:00:00Z"))

    def test_defaults_preserve_all_history_and_current_instant(self):
        now = pd.Timestamp("2026-10-18T10:31:32.123456Z")
        start, end = _research_date_window(now=now)
        self.assertEqual(start, pd.Timestamp("1999-12-31T18:30:00Z"))
        self.assertEqual(end, now)

    def test_invalid_or_empty_windows_are_rejected(self):
        for lower, upper in (("2025-12-11", "2025-12-10"),
                             ("2025-12-10T04:00Z", "2025-12-10T04:00Z"),
                             ("2025-02-29", "2025-03-01"),
                             ("bad", "2025-12-10"), (" ", "2025-12-10"),
                             ("2025-12-10", "NaT"),
                             (True, "2025-12-10"), ([], "2025-12-10"),
                             ("2025-12-10", 20251211),
                             ("2025-12-10", "2025-12-10T04:30:00.000000001Z")):
            with self.subTest(lower=lower, upper=upper), self.assertRaises(ValueError):
                _research_date_window(lower, upper)


class TestResearchWindowRoutes(unittest.TestCase):
    def setUp(self):
        self.route = fixtures.TestStoryOutcomeRoute()
        self.route.setUp()
        self.start = pd.Timestamp("2025-11-19T18:30:00Z")
        self.end = pd.Timestamp("2025-12-10T18:30:00Z")
        self.request = {"symbol": "ITC", "timeframe": "5m",
                        "from_date": "2025-11-20", "to_date": "2025-12-10"}

    def assert_window(self, sql, params, alias=""):
        self.assertNotIn("BETWEEN", sql.upper())
        self.assertIn(f"{alias}ts >= %s AND {alias}ts < %s", sql)
        self.assertEqual(params[-2:], [self.start, self.end])

    def test_outcome_reads_and_cleanup_share_exact_half_open_bounds(self):
        times = [self.start - pd.Timedelta(microseconds=1), self.start,
                 pd.Timestamp("2025-12-10T03:45:00Z"),
                 self.end - pd.Timedelta(microseconds=1), self.end]
        base = self.route.frame().iloc[0].to_dict()
        frame = pd.DataFrame([{**copy.deepcopy(base), "ts": ts, "story_regime": "TRANSITION"}
                              for ts in times])
        schemas = {"market_context": set(fixtures.strategy.STORY_INPUT_COLUMNS) | {"phase_reason"},
                   "strategy_outcomes": set(fixtures.strategy.OUTCOME_STORY_COLUMNS)}
        existing = list(times)
        observed = []

        def read(sql, conn, params):
            alias = "i." if "FROM indicators i" in sql else ""
            self.assert_window(sql, params, alias)
            observed.append(sql)
            if alias:
                return frame.loc[(frame.ts >= params[-2]) & (frame.ts < params[-1])].copy()
            return pd.DataFrame()

        def cleanup(sql, params):
            self.assertIn("DELETE FROM strategy_outcomes", sql)
            self.assert_window(sql, list(params))
            existing[:] = [ts for ts in existing if not params[-2] <= ts < params[-1]]

        with patch.object(fixtures.strategy, "get_db_conn", return_value=self.route.conn), \
             patch.object(fixtures.strategy, "_outcome_schema_columns", return_value=schemas), \
             patch.object(fixtures.strategy, "read_sql_safe", side_effect=read), \
             patch.object(fixtures.strategy, "_load_phase_params", return_value={}), \
             patch.object(fixtures.strategy, "_chunk_execute") as write:
            self.route.cur.execute.side_effect = cleanup
            response = self.route.client.post("/api/offline/calc-strategy-outcomes", json=self.request)
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(response.json["input_rows"], 3)
        self.assertEqual(len(observed), 3)  # indicators/context, rule flags, ORB snapshots
        self.assertEqual(existing, [times[0], times[-1]])
        write.assert_not_called()
        self.assertEqual(response.json["date_window"]["to_exclusive"], self.end.isoformat())

    def test_diagnostic_mode_reports_identical_window_without_cleanup(self):
        response = self.route.run_route(params={**self.request, "diagnostic_mode": True})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["date_window"], {
            "calendar_timezone": "Asia/Kolkata",
            "from_inclusive": self.start.isoformat(), "to_exclusive": self.end.isoformat(),
        })
        for query in self.route.queries:
            self.assert_window(query.args[0], query.kwargs["params"],
                               "i." if "FROM indicators i" in query.args[0] else "")
        self.route.cur.execute.assert_not_called()

    def test_calibration_queries_and_saved_inclusive_metadata(self):
        count = pd.DataFrame([{"total_rows": 5, "has_horizon_mfe": 5, "has_horizon_mae": 5,
                               "has_horizon_mfe_r": 5, "has_horizon_mae_r": 5, "has_exit_after": 5}])
        samples = pd.DataFrame([{
            "market_phase": "TREND_CONTINUATION", "mfe": 2., "mae": -.8,
            "mfe_r": 2., "mae_r": -.8, "exit_after_candles": 3,
            "horizon_mfe": 2., "horizon_mae": -.8, "horizon_mfe_r": 2., "horizon_mae_r": -.8,
            "realized_r": .5, "atr_14": 1., "reference_price": 100.,
        }]*5)
        with patch.object(fixtures.strategy, "get_db_conn", return_value=self.route.conn), \
             patch.object(fixtures.strategy, "read_sql_safe", side_effect=[count, samples]) as read, \
             patch.object(fixtures.strategy, "_chunk_execute") as write:
            response = self.route.client.post("/api/offline/calibrate-phase-params", json={
                **self.request, "min_samples": 5,
            })
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(read.call_count, 2)
        self.assert_window(read.call_args_list[0].args[0], read.call_args_list[0].kwargs["params"])
        self.assert_window(read.call_args_list[1].args[0], read.call_args_list[1].kwargs["params"], "so.")
        self.assertTrue(write.called)
        stored = write.call_args.args[2][0]
        self.assertEqual(stored[-2], self.start)
        self.assertEqual(stored[-1], self.end - pd.Timedelta(microseconds=1))
        self.assertEqual(response.json["date_window"]["to_exclusive"], self.end.isoformat())
        self.assertEqual(response.json["calibrated_to"], stored[-1].isoformat())

    def test_adjacent_day_windows_are_safe_without_changing_overlap_guard(self):
        # New calibration metadata remains inclusive, ending just before Dec 11 IST.
        calibrated = {"BEAR_TREND_ACCEPTANCE": {
            "tp": 2., "sl": 2., "lookahead_min": 15, "viable": True,
            "calibrated_to": (self.end - pd.Timedelta(microseconds=1)).isoformat(),
        }}
        response = self.route.run_route(calibrated=calibrated, params={
            "from_date": "2025-12-11", "to_date": "2025-12-11",
        })
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json["params_overlap_warning"])
        # A legacy inclusive calibration timestamp exactly at entry is still protected.
        calibrated["BEAR_TREND_ACCEPTANCE"]["calibrated_to"] = self.end.isoformat()
        response = self.route.run_route(calibrated=calibrated, params={
            "from_date": "2025-12-11", "to_date": "2025-12-11",
        })
        self.assertTrue(response.json["params_overlap_warning"])

    def test_invalid_dates_return_400_before_any_database_access(self):
        for endpoint in ("calc-strategy-outcomes", "calibrate-phase-params"):
            for changes in ({"to_date": "bad"}, {"from_date": "2025-12-11"}):
                with self.subTest(endpoint=endpoint, changes=changes), \
                     patch.object(fixtures.strategy, "get_db_conn") as db:
                    response = self.route.client.post(f"/api/offline/{endpoint}",
                                                       json={**self.request, **changes})
                    self.assertEqual(response.status_code, 400)
                    db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
