import os
import sys
import unittest

import numpy as np
import pandas as pd


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.ml import (  # noqa: E402
    PHASE_TO_EXEC,
    _cost_r_feature,
    _resolve_exec_direction,
    _walk_forward_splits,
)
from routes.strategy import _session_vix_level  # noqa: E402
from routes.strategy_logic import (  # noqa: E402
    PHASE_MODEL,
    PHASE_TO_ML,
    _derive_market_story,
    _post_impulse_trend_phase,
    _simulate_exit_vectorized,
)


class TestStrategyRegressions(unittest.TestCase):
    def test_all_missing_vix_is_numeric_and_safe_to_diff(self):
        frame = pd.DataFrame(
            {
                "date": ["2026-09-18", "2026-09-18", "2026-09-19"],
                "vix": [None, None, None],
            }
        )

        level = _session_vix_level(frame)

        self.assertTrue(pd.api.types.is_numeric_dtype(level))
        self.assertTrue(level.isna().all())
        self.assertEqual(level.diff().fillna(0).tolist(), [0.0, 0.0, 0.0])

    def test_vix_coercion_and_fill_stay_within_session(self):
        frame = pd.DataFrame(
            {
                "date": ["2026-09-18", "2026-09-18", "2026-09-19", "2026-09-19"],
                "vix": ["14.5", None, None, "16.0"],
            }
        )

        level = _session_vix_level(frame)

        self.assertEqual(level.iloc[:2].tolist(), [14.5, 14.5])
        self.assertTrue(pd.isna(level.iloc[2]))
        self.assertEqual(level.iloc[3], 16.0)

    def test_long_exit_keeps_full_horizon_excursions(self):
        result = _simulate_exit_vectorized(
            entry=100.0,
            tp=102.0,
            sl=98.0,
            highs=np.array([102.5, 105.0]),
            lows=np.array([99.0, 97.0]),
            closes=np.array([102.0, 100.0]),
            n=1,
            is_short=False,
            excursion_n=2,
        )
        self.assertEqual(result[:3], ("TP_HIT", 102.0, 1))
        self.assertEqual(result[3], 5.0)
        self.assertEqual(result[4], -3.0)

    def test_short_exit_keeps_full_horizon_excursions(self):
        result = _simulate_exit_vectorized(
            entry=100.0,
            tp=98.0,
            sl=102.0,
            highs=np.array([101.0, 104.0]),
            lows=np.array([97.5, 95.0]),
            closes=np.array([98.0, 100.0]),
            n=1,
            is_short=True,
            excursion_n=2,
        )
        self.assertEqual(result[:3], ("TP_HIT", 98.0, 1))
        self.assertEqual(result[3], 5.0)
        self.assertEqual(result[4], -4.0)

    def test_same_bar_tp_and_sl_is_conservative_loss(self):
        result = _simulate_exit_vectorized(
            entry=100.0,
            tp=102.0,
            sl=98.0,
            highs=np.array([103.0]),
            lows=np.array([97.0]),
            closes=np.array([100.0]),
            n=1,
            is_short=False,
        )
        self.assertEqual(result[0], "SL_HIT")

    def test_bear_post_impulse_never_gets_bull_phase(self):
        self.assertEqual(
            _post_impulse_trend_phase("BEAR", close=99.0, open_=100.0),
            "BEAR_TREND_CONTINUATION",
        )
        self.assertEqual(
            _post_impulse_trend_phase("BEAR", close=101.0, open_=100.0),
            "BEAR_TREND_DIGESTION",
        )

    def test_story_regime_requires_confirmation_and_routes_reversal_through_transition(self):
        bull = [True, True, True, False, False, False, False]
        frame = pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-09-18").date()] * 7,
                "market_phase": ["TREND_CONTINUATION"] * 3
                + ["BEAR_TREND_CONTINUATION"] * 4,
                "open": [100.0] * 7,
                "close": [101.0 if is_bull else 99.0 for is_bull in bull],
                "ema_9": [103.0 if is_bull else 97.0 for is_bull in bull],
                "ema_21": [102.0 if is_bull else 98.0 for is_bull in bull],
                "ema_50": [101.0 if is_bull else 99.0 for is_bull in bull],
                "ema_21_slope": [0.03 if is_bull else -0.03 for is_bull in bull],
                "atr_14": [1.0] * 7,
                "vwap_dist_atr": [1.0 if is_bull else -1.0 for is_bull in bull],
                "price_structure": ["BULL" if is_bull else "BEAR" for is_bull in bull],
                "vol_ratio": [2.0] * 7,
                "obv_slope": [1.0 if is_bull else -1.0 for is_bull in bull],
                "range_efficiency": [0.7] * 7,
                "atr_expanding": [1] * 7,
                "candle_overlap": [0] * 7,
                "gap_atr": [0.0] * 7,
                "_phase_reason": ["test"] * 7,
            }
        )

        result = _derive_market_story(frame)

        self.assertEqual(result.loc[2, "story_regime"], "BULL_TREND")
        self.assertEqual(result.loc[3, "story_regime"], "TRANSITION")
        self.assertEqual(result.loc[5, "story_regime"], "BEAR_TREND")
        self.assertFalse(
            any(
                left == "BULL_TREND" and right == "BEAR_TREND"
                for left, right in zip(
                    result["story_regime"], result["story_regime"].iloc[1:]
                )
            )
        )
        self.assertTrue(result["regime_rule_score"].between(0, 1).all())
        self.assertTrue(result["event_rule_score"].between(0, 1).all())
        self.assertEqual(set(result["bar_event"]), {"CONTINUATION"})

    def test_strategy_and_ml_execution_contract(self):
        expected = {
            "LARGE_GAP_UP": ("SHORT", "FADE_GAP_UP"),
            "MODERATE_GAP_DOWN": ("SHORT", "FOLLOW_GAP_DOWN"),
            "GAP_UP_FADE": ("SHORT", "FADE_GAP_UP"),
            "GAP_DOWN_FADE": ("LONG", "FADE_GAP_DOWN"),
            "PULLBACK_FAIL": ("NEUTRAL", "SKIP"),
            "REJECTION": ("NEUTRAL", "SKIP"),
            "DISTRIBUTION": ("NEUTRAL", "SKIP"),
        }
        for phase, (strategy_direction, exec_class) in expected.items():
            self.assertEqual(PHASE_MODEL[phase]["dir"], strategy_direction)
            self.assertEqual(PHASE_TO_EXEC[phase], exec_class)

        self.assertEqual(PHASE_TO_ML["PULLBACK_FAIL"], "NEUTRAL")
        self.assertEqual(PHASE_TO_ML["REJECTION"], "NEUTRAL")
        self.assertIn("AUCTION_IMPULSE_UP", PHASE_MODEL)
        self.assertIn("AUCTION_IMPULSE_DOWN", PHASE_MODEL)

    def test_dynamic_execution_direction(self):
        self.assertEqual(
            _resolve_exec_direction("FOLLOW_GAP", {"gap_atr": -1.2}), "SHORT"
        )
        self.assertEqual(
            _resolve_exec_direction(
                "FOLLOW_MOMENTUM", {"gap_atr": 0, "ema_21_slope": 0.2}
            ),
            "LONG",
        )

    def test_cost_feature_is_risk_normalized(self):
        row = {"atr_14": 2.0, "reference_price": 100.0}
        # FOLLOW_GAP uses a 0.7 ATR stop: 0.15 / 1.4 = 0.107142...
        self.assertAlmostEqual(_cost_r_feature(row, "FOLLOW_GAP"), 0.15 / 1.4)

    def test_walk_forward_folds_do_not_overlap_and_purge_open_labels(self):
        ts = pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC")
        frame = pd.DataFrame({"ts": ts, "exit_ts": ts + pd.Timedelta(hours=5)})
        splits = _walk_forward_splits(frame, n_splits=3, test_frac=0.2)

        self.assertEqual(len(splits), 3)
        test_indexes = []
        for train, test in splits:
            self.assertTrue((train["exit_ts"] < test["ts"].iloc[0]).all())
            test_indexes.extend(test.index.tolist())
        self.assertEqual(len(test_indexes), len(set(test_indexes)))


if __name__ == "__main__":
    unittest.main()
