"""Story eligibility, excursion semantics and mocked-DB route integration."""
import json
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from flask import Flask
from psycopg2 import sql as pg_sql

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes import strategy  # noqa: E402
from routes.strategy_logic import (  # noqa: E402
    _directional_excursion,
    _legacy_trade_direction,
    _outcome_excursions,
    _resolve_story_trade,
    _simulate_exit_vectorized,
    _story_trade_context,
)


def render_sql(query):
    """Render composables for mocked-DB assertions, without a live connection."""
    if not isinstance(query, pg_sql.Composable):
        return query
    # Only replace the connection-dependent quoting primitive in these unit tests.
    with patch("psycopg2.extensions.quote_ident",
               side_effect=lambda name, context: '"' + name.replace('"', '""') + '"'):
        return query.as_string(None)


def story(**changes):
    value = {
        "story_regime": "BULL_TREND", "bar_event": "CONTINUATION",
        "regime_rule_score": 0.80, "event_rule_score": 0.75,
        "regime_age_bars": 3, "candidate_regime": "BULL_TREND",
        "candidate_age_bars": 5, "candidate_rule_score": 0.80,
        "regime_reason_code": "REGIME_EVIDENCE_CONFIRMED",
        "event_reason_code": "EVENT_CONTINUATION", "story_version": 1,
        "directional_edge": 0.65, "bull_score": 0.80, "bear_score": 0.15,
        "reason_details": {"directional_edge": 0.65, "bull_score": 0.80, "bear_score": 0.15},
    }
    value.update(changes)
    return value


class TestStoryEligibility(unittest.TestCase):
    def test_bull_continuation(self):
        result = _resolve_story_trade(story())
        self.assertTrue(result["eligible"])
        self.assertEqual(result["trade_direction"], "LONG")
        self.assertEqual(result["setup_key"], "BULL_TREND:CONTINUATION:LONG")

    def test_bear_acceptance(self):
        result = _resolve_story_trade(story(
            story_regime="BEAR_TREND", candidate_regime="BEAR_TREND",
            directional_edge=-0.66, bar_event="ACCEPTANCE",
        ))
        self.assertEqual(result["trade_direction"], "SHORT")
        self.assertEqual(result["eligibility_reason"], "VALID_BEAR_SETUP")

    def test_context_regimes_and_events(self):
        for regime, event, reason in (
            ("TRANSITION", "IMPULSE", "REGIME_TRANSITION"),
            ("RANGE", "CONTINUATION", "REGIME_RANGE"),
            ("BULL_TREND", "DIGESTION", "EVENT_CONTEXT_ONLY"),
            ("BULL_TREND", "PAUSE", "EVENT_CONTEXT_ONLY"),
            ("BULL_TREND", "CHOP", "EVENT_CONTEXT_ONLY"),
            ("BULL_TREND", "ABSORPTION", "EVENT_CONTEXT_ONLY"),
            ("BULL_TREND", "DISTRIBUTION", "EVENT_CONTEXT_ONLY"),
            ("BULL_TREND", "REJECTION", "EVENT_CONTEXT_ONLY"),
            ("BULL_TREND", "COMPRESSION", "EVENT_CONTEXT_ONLY"),
            (None, "CONTINUATION", "MISSING_STORY_CONTEXT"),
        ):
            with self.subTest(regime=regime, event=event):
                result = _resolve_story_trade(story(story_regime=regime, bar_event=event))
                self.assertFalse(result["eligible"])
                self.assertEqual(result["eligibility_reason"], reason)

    def test_bear_digestion_and_wrong_edge(self):
        context = story(story_regime="BEAR_TREND", candidate_regime="BEAR_TREND")
        for event, edge, reason in (("DIGESTION", -0.7, "EVENT_CONTEXT_ONLY"),
                                    ("ACCEPTANCE", 0.7, "WEAK_DIRECTIONAL_EDGE")):
            context.update(bar_event=event, directional_edge=edge)
            self.assertEqual(_resolve_story_trade(context)["eligibility_reason"], reason)

    def test_confirmation_and_challengers(self):
        for changes, reason in (
            ({"candidate_regime": "BEAR_TREND"}, "OPPOSING_CANDIDATE"),
            ({"candidate_regime": "RANGE"}, "REGIME_NOT_CONFIRMED"),
            ({"candidate_regime": "TRANSITION"}, "REGIME_NOT_CONFIRMED"),
            ({"regime_reason_code": "REGIME_RETAINED_PENDING_CONFIRMATION"}, "REGIME_NOT_CONFIRMED"),
            ({"regime_reason_code": None}, "REGIME_NOT_CONFIRMED"),
            ({"regime_age_bars": 1}, "REGIME_TOO_YOUNG"),
            ({"regime_rule_score": 0.59}, "LOW_REGIME_SCORE"),
            ({"event_rule_score": 0.49}, "LOW_EVENT_SCORE"),
            ({"directional_edge": 0.24}, "WEAK_DIRECTIONAL_EDGE"),
        ):
            with self.subTest(changes=changes):
                self.assertEqual(_resolve_story_trade(story(**changes))["eligibility_reason"], reason)

    def test_threshold_boundaries_and_configurable_policy(self):
        context = story(regime_rule_score=.60, event_rule_score=.50,
                        regime_age_bars=2, directional_edge=.25)
        self.assertTrue(_resolve_story_trade(context)["eligible"])
        self.assertFalse(_resolve_story_trade(context, min_directional_edge=.3)["eligible"])
        self.assertTrue(_resolve_story_trade(story(
            candidate_regime="BEAR_TREND", candidate_age_bars=0,
        ))["eligible"])
        self.assertTrue(_resolve_story_trade(story(
            regime_reason_code="REGIME_CANDIDATE_CONFIRMED",
        ))["eligible"])

    def test_gap_resolution_uses_actual_direction(self):
        expected = {"LONG": "LONG", "SHORT": "SHORT", "FOLLOW": "SHORT",
                    "FADE": "SHORT", "MEAN": "LONG", "BREAKOUT": "SHORT",
                    "NEUTRAL": None}
        for token, direction in expected.items():
            with self.subTest(token=token):
                resolved = _legacy_trade_direction(token, -1, -.2, "BULL", -.1)
                self.assertEqual(resolved, direction)
        result = _resolve_story_trade(story(
            story_regime="GAP_AUCTION", bar_event="GAP_CONTINUATION",
        ), gap_direction="SHORT")
        self.assertEqual(result["setup_key"], "GAP_AUCTION:GAP_CONTINUATION:SHORT")
        self.assertFalse(_resolve_story_trade(story(
            story_regime="GAP_AUCTION", bar_event="CHOP",
        ), gap_direction="SHORT")["eligible"])

    def test_bad_json_and_nonfinite_evidence_fail_closed(self):
        for details in (None, "broken", "[]", [], {"directional_edge": True}, {"directional_edge": "NaN"},
                        {"directional_edge": "Infinity"}, {"directional_edge": {}}):
            context = story(reason_details=details)
            context.pop("directional_edge")
            self.assertFalse(_resolve_story_trade(_story_trade_context(context))["eligible"])
        context = story(reason_details='{"directional_edge": "0.65", "bull_score": null}')
        context.pop("directional_edge")
        normalized = _story_trade_context(context)
        self.assertEqual(normalized["directional_edge"], .65)
        self.assertTrue(_resolve_story_trade(normalized)["eligible"])

    def test_nullable_string_context_is_not_a_trade(self):
        result = _resolve_story_trade(story(story_regime=pd.NA))
        self.assertEqual(result["eligibility_reason"], "MISSING_STORY_CONTEXT")


class TestExcursionWindows(unittest.TestCase):
    def test_short_sign_and_zero_clamps(self):
        self.assertEqual(_directional_excursion(100, [101, 104], [98, 95], 2, True), (5, -4))
        self.assertEqual(_directional_excursion(100, [99], [98], 1), (0, -2))
        self.assertEqual(_directional_excursion(100, [99], [98], 1, True), (2, 0))

    def test_exit_bar_then_later_adverse_moves_are_separate(self):
        for short in (False, True):
            h = np.array([101, 105, 110]) if short else np.array([103, 104, 105])
            l = np.array([97, 96, 95]) if short else np.array([99, 95, 90])
            result = _outcome_excursions(100, h, l, 1, 2, 2, short)
            self.assertEqual(result["trade_mae"], -1)
            self.assertEqual(result["horizon_mae"], -5)
            self.assertEqual(result["session_mae"], -10)
            self.assertEqual(result["trade_mae_r"], -.5)

    def test_same_bar_tie_remains_sl_first_for_both_directions(self):
        for short, tp, sl in ((False, 102, 98), (True, 98, 102)):
            result = _simulate_exit_vectorized(100, tp, sl, np.array([103]),
                                               np.array([97]), np.array([100]), 1, short)
            self.assertEqual(result[:3], ("SL_HIT", sl, 1))

    def test_invalid_risk_and_empty_windows(self):
        for risk in (0, -1, np.nan, np.inf):
            with self.subTest(risk=risk), self.assertRaises(ValueError):
                _outcome_excursions(100, [101], [99], 1, 1, risk)
        self.assertEqual(_directional_excursion(100, [], [], 2), (0, 0))
        with self.assertRaises(ValueError):
            _directional_excursion(100, [np.nan], [99], 1)


class TestStoryOutcomeRoute(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(strategy.strategy_bp)
        self.client = app.test_client()
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.written = []
        self.insert_sql = None

    def frame(self, **signal_changes):
        rows = []
        for i in range(13):
            ts = pd.Timestamp("2026-10-16 04:00:00Z") + pd.Timedelta(minutes=5*i)
            if i == 12:
                ts = pd.Timestamp("2026-10-17 04:00:00Z")
            value = {
                "ts": ts, "open": 100., "close": 101., "high": 102., "low": 99.5,
                "atr_14": 1., "market_phase": "BEAR_TREND_ACCEPTANCE",
                "minute_of_day": 15+5*i, "minute_of_day_mc": 15+5*i,
                "ema_21_slope": .1, "vwap_dist_pct": .01, "range_efficiency": .7,
                "macro_regime": "NEUTRAL_MACRO", "price_structure": "BULL",
                "trend_exhaustion": 0, "gap_atr": 0., "impulse_dir": "BULL",
                "phase_reason": "Legacy explanation", **story(),
            }
            if i > 0:
                value["story_regime"] = "TRANSITION"
            if i == 2:
                value["low"] = 97.
            if i == 10:
                value["low"] = 90.
            if i == 12:
                value["low"] = 1.  # must not leak into previous session excursion
            rows.append(value)
        rows[0].update(signal_changes)
        return pd.DataFrame(rows)

    def run_route(self, frame=None, params=None, missing=None, calibrated=None):
        frame = frame if frame is not None else self.frame()
        schema = {
            "market_context": set(strategy.STORY_INPUT_COLUMNS) | {"phase_reason"},
            "strategy_outcomes": set(strategy.OUTCOME_STORY_COLUMNS),
        }
        if missing:
            table, name = missing
            schema[table].remove(name)

        def capture(cur, sql, rows):
            self.insert_query = sql
            sql = render_sql(sql)
            self.insert_sql = sql
            columns = re.search(r"INSERT INTO strategy_outcomes\s*\((.*?)\)\s*VALUES", sql, re.S).group(1)
            columns = [name.strip().strip('"') for name in columns.split(",")]
            for row in rows:
                self.assertEqual(len(columns), len(row))
                self.written.append(dict(zip(columns, row)))

        with patch.object(strategy, "get_db_conn", return_value=self.conn), \
             patch.object(strategy, "_outcome_schema_columns", return_value=schema), \
             patch.object(strategy, "read_sql_safe", side_effect=[frame, pd.DataFrame(), pd.DataFrame()]) as read, \
             patch.object(strategy, "_load_phase_params", return_value=calibrated or {}), \
             patch.object(strategy, "_chunk_execute", side_effect=capture):
            response = self.client.post("/api/offline/calc-strategy-outcomes", json={
                "symbol": "ITC", "timeframe": "5m", **(params or {}),
            })
            self.queries = read.call_args_list
        return response

    def test_story_overrides_bear_legacy_direction_and_persists_all_windows(self):
        response = self.run_route()
        self.assertEqual(response.status_code, 200, response.json)
        result = response.json
        self.assertEqual(result["rows_written"], 1)
        self.assertEqual(result["input_rows"], result["rows_written"] + result["total_skipped"])
        row = self.written[0]
        self.assertEqual(row["market_phase"], "BEAR_TREND_ACCEPTANCE")
        self.assertEqual(row["trade_direction"], "LONG")
        self.assertEqual(row["setup_key"], "BULL_TREND:CONTINUATION:LONG")
        self.assertEqual(row["phase_reason"], "Legacy explanation")
        self.assertEqual(row["exit_reason"], "TP_HIT")
        self.assertEqual(row["exit_after_candles"], 1)
        self.assertAlmostEqual(row["trade_mae"], -.55)
        self.assertAlmostEqual(row["horizon_mae"], -3.05)
        self.assertAlmostEqual(row["session_mae"], -10.05)
        self.assertEqual(row["mae"], row["session_mae"])
        self.assertEqual(row["mfe_r"], row["session_mfe_r"])
        self.assertAlmostEqual(row["realized_r_gross"] - row["cost_r"], row["realized_r"])
        self.assertEqual(json.loads(row["reason_details"])["directional_edge"], .65)
        self.assertEqual(row["exit_ts"], pd.Timestamp("2026-10-16 04:05:00").to_pydatetime())
        # Timezone normalization remains UTC-naive for the existing DB writer.
        self.assertIsNone(row["ts"].tzinfo)
        for name in strategy.STORY_INPUT_COLUMNS:
            self.assertIn(f'"mc"."{name}"', render_sql(self.queries[0].args[0]))

    def test_composed_queries_keep_identifiers_and_request_values_separate(self):
        symbol = "ITC'; DROP TABLE strategy_outcomes; --"
        response = self.run_route(params={"symbol": symbol})
        self.assertEqual(response.status_code, 200, response.json)
        query = self.queries[0].args[0]
        self.assertIsInstance(query, pg_sql.Composed)
        rendered = render_sql(query)
        self.assertNotIn(symbol.upper(), rendered)
        self.assertEqual(self.queries[0].kwargs["params"][0], symbol.upper())
        self.assertEqual(rendered.count("%s"), 5)
        self.assertIn('"mc"."phase_reason"', rendered)
        self.assertIsInstance(self.insert_query, pg_sql.Composed)
        self.assertEqual(self.insert_sql.count("%s"), 1)
        for name in strategy.OUTCOME_STORY_COLUMNS:
            self.assertIn(f'"{name}"="excluded"."{name}"', self.insert_sql)

    def test_optional_phase_reason_column_uses_fixed_null_projection(self):
        response = self.run_route(missing=("market_context", "phase_reason"))
        self.assertEqual(response.status_code, 200, response.json)
        rendered = render_sql(self.queries[0].args[0])
        self.assertIn("NULL::text AS phase_reason", rendered)
        self.assertNotIn('"mc"."phase_reason"', rendered)

    def test_bear_story_overrides_bull_legacy_phase(self):
        response = self.run_route(self.frame(
            market_phase="TREND_ACCEPTANCE", close=99., price_structure="BEAR",
            story_regime="BEAR_TREND", candidate_regime="BEAR_TREND",
            reason_details={"directional_edge": -.7}, directional_edge=-.7,
        ))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.written[0]["trade_direction"], "SHORT")

    def test_all_context_only_replaces_stale_window_with_no_fake_trades(self):
        frame = self.frame()
        frame["story_regime"] = "TRANSITION"
        response = self.run_route(frame)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["status"], "NO_OUTCOMES")
        self.assertEqual(response.json["skipped_transition"], len(frame))
        self.assertEqual(response.json["total_skipped"], len(frame))
        self.assertEqual(self.written, [])
        self.assertTrue(any("DELETE FROM strategy_outcomes" in call.args[0]
                            for call in self.cur.execute.call_args_list))

    def test_missing_migration_does_not_delete_existing_outcomes(self):
        response = self.run_route(missing=("strategy_outcomes", "trade_mae"))
        self.assertEqual(response.status_code, 409)
        self.cur.execute.assert_not_called()
        self.assertEqual(response.json["missing_columns"]["strategy_outcomes"], ["trade_mae"])

    def test_nullable_story_row_never_falls_back_to_legacy_direction(self):
        response = self.run_route(self.frame(story_regime=pd.NA))
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(response.json["skipped_by_eligibility"]["MISSING_STORY_CONTEXT"], 1)
        self.assertEqual(self.written, [])

    def test_gap_trade_retains_legacy_fade_direction(self):
        response = self.run_route(self.frame(
            story_regime="GAP_AUCTION", bar_event="GAP_OPEN",
            market_phase="LARGE_GAP_UP", gap_atr=1.5, minute_of_day_mc=0,
        ))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.written[0]["trade_direction"], "SHORT")
        self.assertEqual(self.written[0]["setup_key"], "GAP_AUCTION:GAP_OPEN:SHORT")

    def test_safety_gates_still_reject(self):
        for changes, params, reason in (
            ({"macro_regime": "BEAR_MACRO"}, {}, "MACRO_MISMATCH"),
            ({"price_structure": "BEAR"}, {}, "PRICE_STRUCTURE_MISMATCH"),
            ({"trend_exhaustion": 1}, {}, "TREND_EXHAUSTED"),
            ({"close": 99.}, {}, "SIGNAL_DIRECTION_MISMATCH"),
            ({}, {"cost_r_gate": .01}, "COST_GATE"),
            ({"minute_of_day_mc": 320}, {}, "EOD_GATE"),
            ({}, {"min_rules_fired": 1}, "MIN_RULES_GATE"),
            ({"atr_14": 0.}, {}, "INVALID_ATR"),
            ({"atr_14": np.nan}, {}, "INVALID_ATR"),
        ):
            with self.subTest(reason=reason):
                response = self.run_route(self.frame(**changes), params)
                self.assertEqual(response.status_code, 400, response.json)
                self.assertEqual(response.json["skipped_by_safety"].get(reason), 1)
                self.assertEqual(response.json["total_skipped"], response.json["input_rows"])

    def test_no_next_day_entry_and_no_last_bar_entry(self):
        frame = self.frame()
        frame.loc[0, "story_regime"] = "TRANSITION"
        frame.loc[[11, 12], "story_regime"] = "BULL_TREND"
        response = self.run_route(frame)
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(response.json["skipped_by_safety"], {
            "NEXT_BAR_OUTSIDE_SESSION": 1, "NO_NEXT_BAR": 1,
        })

    def test_changing_future_story_does_not_change_current_decision(self):
        frame = self.frame()
        frame.loc[1:, "bar_event"] = "DIGESTION"
        response = self.run_route(frame)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.written[0]["setup_key"], "BULL_TREND:CONTINUATION:LONG")

    def test_calibrated_params_and_overlap_guard_are_preserved(self):
        params = {"BEAR_TREND_ACCEPTANCE": {
            "tp": 2., "sl": 2., "lookahead_min": 15, "viable": True,
            "calibrated_to": "2026-01-01",
        }}
        response = self.run_route(calibrated=params)
        self.assertTrue(response.json["calibrated_params_ignored"])
        self.assertEqual(response.json["param_source"], "default")
        self.written = []
        response = self.run_route(calibrated=params, params={"from_date": "2026-10-01"})
        self.assertEqual(response.json["param_source"], "calibrated")
        self.assertFalse(response.json["params_overlap_warning"])
        self.assertEqual(self.written[0]["lookahead_candles"], 3)

    def test_bad_research_policy_is_rejected_before_database_access(self):
        for policy in ({"min_event_score": "nan"}, {"min_regime_age_bars": 1.5},
                       {"min_regime_score": True}, {"unknown": 1}, []):
            with self.subTest(policy=policy), patch.object(strategy, "get_db_conn") as db:
                response = self.client.post("/api/offline/calc-strategy-outcomes", json={
                    "symbol": "ITC", "timeframe": "5m", "story_policy": policy,
                })
                self.assertEqual(response.status_code, 400)
                db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
