"""TP/SL calibration must not learn post-horizon/session price excursions."""
import copy
import os
import re
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import test_story_outcomes as fixtures  # noqa: E402


class TestHorizonCalibration(unittest.TestCase):
    def setUp(self):
        self.route = fixtures.TestStoryOutcomeRoute()
        self.route.setUp()

    def samples(self):
        return pd.DataFrame([{
            "market_phase": "TREND_CONTINUATION",
            "horizon_mfe": mfe, "horizon_mae": mae,
            "horizon_mfe_r": mfe/2, "horizon_mae_r": mae/2,
            "mfe": 1000., "mae": -1000., "mfe_r": 500., "mae_r": -500.,
            "session_mfe": 1000., "session_mae": -1000.,
            "trade_mfe": .1, "trade_mae": -.1,
            "exit_after_candles": 3, "realized_r": .5, "atr_14": 1., "reference_price": 100.,
        } for mfe, mae in zip([1., 1.5, 2., 2.5, 3.], [-.4, -.6, -.8, -1., -1.2])])

    def calibrate(self, samples):
        self.written = []
        count = pd.DataFrame([{
            "total_rows": 5, "has_horizon_mfe": 5 if not samples.empty else 0,
            "has_horizon_mae": 5, "has_horizon_mfe_r": 5, "has_horizon_mae_r": 5,
            "has_exit_after": 5,
        }])

        def capture(cur, sql, rows):
            names = re.search(r"INSERT INTO phase_params\s*\((.*?)\)\s*VALUES", sql, re.S).group(1)
            columns = [s.strip() for s in names.split(",")]
            for row in rows:
                self.assertEqual(len(columns), len(row))
                self.written.append(dict(zip(columns, row)))

        with patch.object(fixtures.strategy, "get_db_conn", return_value=self.route.conn), \
             patch.object(fixtures.strategy, "read_sql_safe", side_effect=[count, samples.copy()]) as read, \
             patch.object(fixtures.strategy, "_chunk_execute", side_effect=capture), \
             patch.object(fixtures.strategy, "invalidate_phase_params_cache"):
            response = self.route.client.post("/api/offline/calibrate-phase-params", json={
                "symbol": "ITC", "timeframe": "5m", "min_samples": 5,
            })
        self.queries = read.call_args_list
        return response

    def test_queries_and_percentiles_use_only_horizon_excursions(self):
        samples = self.samples()
        response = self.calibrate(samples)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["excursion_source"], "horizon")
        phase = response.json["phases"]["TREND_CONTINUATION"]
        self.assertEqual(phase["p25_mfe_atr"], 1.5)
        self.assertEqual(phase["p50_mfe_atr"], 2.)
        self.assertEqual(phase["p75_mfe_atr"], 2.5)
        self.assertEqual(phase["selected_mae_atr"], 1.)
        stored = self.written[0]
        self.assertEqual(stored["optimal_tp"], np.percentile(samples.horizon_mfe, 40))
        self.assertEqual(stored["avg_mfe_r"], samples.horizon_mfe_r.mean())
        self.assertEqual(stored["avg_mae_r"], samples.horizon_mae_r.mean())
        for percentile in (25, 50, 75):
            self.assertEqual(stored[f"p{percentile}_mfe_r"], np.percentile(samples.horizon_mfe_r, percentile))
        self.assertEqual(stored["p25_mae_r"], np.percentile(samples.horizon_mae_r, 25))
        for query in self.queries:
            sql = query.args[0]
            for name in ("horizon_mfe", "horizon_mae", "horizon_mfe_r", "horizon_mae_r"):
                self.assertIn(name, sql)
            self.assertIsNone(re.search(r"\bso\.(?:mfe|mae|mfe_r|mae_r)\b|COUNT\((?:mfe|mae)\)", sql))
        sql = self.queries[1].args[0]
        for name in ("horizon_mfe", "horizon_mae", "horizon_mfe_r", "horizon_mae_r"):
            self.assertIn(f"so.{name} IS NOT NULL", sql)

    def test_later_session_or_trade_excursions_cannot_change_parameters(self):
        first = self.calibrate(self.samples()).json
        first_values = copy.deepcopy(self.written[0])
        samples = self.samples()
        samples[["mfe", "mae", "mfe_r", "mae_r", "session_mfe", "session_mae", "trade_mfe", "trade_mae"]] *= 100
        second = self.calibrate(samples).json
        self.assertEqual(first["phases"], second["phases"])
        for field, value in first_values.items():
            if field not in ("computed_at", "calibrated_to"):
                self.assertEqual(value, self.written[0][field], field)

    def test_legacy_rows_without_horizon_data_never_fall_back(self):
        response = self.calibrate(pd.DataFrame())
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["status"], "NO_DATA")
        self.assertIn("horizon", response.json["message"])
        self.assertEqual(self.written, [])

    def test_nonfinite_horizon_values_are_not_calibration_samples(self):
        samples = self.samples()
        samples.loc[0, "horizon_mfe_r"] = np.inf
        response = self.calibrate(samples)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["phases"]["TREND_CONTINUATION"]["status"],
                         "INSUFFICIENT_VALID_HORIZON_DATA")
        self.assertEqual(self.written, [])


if __name__ == "__main__":
    unittest.main()
