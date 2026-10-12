"""Opt-in integration test for the live Yahoo Finance adapter."""

from __future__ import annotations

import os
import unittest

import pandas as pd
from app.quant.data import STANDARD_COLUMNS, load_stock_data

RUN_LIVE_TESTS = os.getenv("QUANTAI_RUN_LIVE_TESTS") == "1"


@unittest.skipUnless(RUN_LIVE_TESTS, "set QUANTAI_RUN_LIVE_TESTS=1 to access live data")
class LiveDataLoaderTests(unittest.TestCase):
    def test_aapl_daily_history_satisfies_contract(self) -> None:
        frame = load_stock_data("AAPL", start="2015-01-01")

        self.assertFalse(frame.empty)
        self.assertEqual(tuple(frame.columns), STANDARD_COLUMNS)
        self.assertIsInstance(frame.index, pd.DatetimeIndex)
        self.assertTrue(frame.index.is_monotonic_increasing)
        self.assertTrue(frame.index.is_unique)
        self.assertFalse(frame.isna().any().any())
        self.assertLessEqual(frame.index.min(), pd.Timestamp("2015-01-10"))
        self.assertTrue(frame["volume"].ge(0).all())
        self.assertTrue((frame["high"] >= frame["low"]).all())


if __name__ == "__main__":
    unittest.main()
