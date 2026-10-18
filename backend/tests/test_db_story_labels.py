"""Regression: leading SQL NULLs must not erase pandas 3 string story labels."""
from decimal import Decimal
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db import read_sql_safe
from routes import strategy_comparison as research


class TestReadSqlStoryLabels(unittest.TestCase):
    def read(self, rows):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchall.return_value = rows
        return read_sql_safe("SELECT fixture", connection)

    def test_azure_16725_bars_16650_labels_and_75_missing_per_symbol(self):
        rows = [{"symbol": symbol, "story_regime": None if i < 75 else "BULL_TREND",
                 "bar_event": None if i < 75 else "CONTINUATION",
                 "market_phase": None if i < 75 else "TREND_ACCEPTANCE",
                 "atr_14": Decimal("1.25")}
                for symbol in ("ITC", "TATASTEEL") for i in range(16725)]
        # Exercise pandas 3's inferred string dtype explicitly; a first missing
        # string scalar is float NaN. This failed with the old None-only check.
        with pd.option_context("future.infer_string", True):
            raw = pd.DataFrame(rows)
            self.assertTrue(pd.isna(raw.story_regime.iloc[0]))
            frame = self.read(rows)
        for symbol, group in frame.groupby("symbol"):
            self.assertEqual(len(group), 16725, symbol)
            self.assertEqual(group.story_regime.notna().sum(), 16650, symbol)
            self.assertEqual(group.bar_event.notna().sum(), 16650, symbol)
            self.assertEqual(group.market_phase.notna().sum(), 16650, symbol)
            self.assertEqual(group.story_regime.isna().sum(), 75, symbol)
            self.assertEqual(group.atr_14.iloc[0], 1.25)

    def test_nan_none_and_pd_na_do_not_imply_numeric_text_column(self):
        for missing in (None, np.nan, pd.NA):
            with self.subTest(missing=repr(missing)):
                frame = self.read([{"story_regime": missing, "details": None},
                                   {"story_regime": "BEAR_TREND", "details": {"directional_edge": -.6}}])
                self.assertEqual(frame.story_regime.iloc[1], "BEAR_TREND")
                self.assertEqual(frame.details.iloc[1], {"directional_edge": -.6})

    def test_all_missing_and_numeric_decimal_columns_remain_compatible(self):
        frame = self.read([{"value": None, "price": None}, {"value": None, "price": Decimal("100.5")}])
        self.assertTrue(frame.value.isna().all())
        self.assertEqual(frame.price.iloc[1], 100.5)

    def test_diagnostics_distinguish_sql_dataframe_and_processing_loss(self):
        diagnostics = {"sql_counts": {s: {"indicator_rows": 16725, "nonnull_story_regime": 16650}
                                      for s in research.SYMBOLS},
                       "after_read_sql_safe": {s: {"indicator_rows": 16725, "nonnull_story_regime": 0}
                                               for s in research.SYMBOLS}}
        self.assertEqual(set(research._label_loss_stages(diagnostics).values()), {"DATAFRAME_RETRIEVAL_MISMATCH"})
        for row in diagnostics["after_read_sql_safe"].values():
            row["nonnull_story_regime"] = 16650
        self.assertEqual(set(research._label_loss_stages(diagnostics).values()), {"CONSISTENT"})
        diagnostics["after_compare_symbol"] = {s: {"nonnull_story_regime": 0} for s in research.SYMBOLS}
        self.assertEqual(set(research._label_loss_stages(diagnostics).values()), {"IN_MEMORY_PROCESSING_MISMATCH"})


if __name__ == "__main__":
    unittest.main()
