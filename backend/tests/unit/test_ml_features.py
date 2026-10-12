"""Tests for leakage-aware machine-learning feature construction."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
from app.quant.ml.features import build_ml_dataset, split_time_series_dataset


def sample_market_data(periods: int = 220) -> pd.DataFrame:
    index = pd.bdate_range("2023-01-02", periods=periods, name="date")
    step = np.arange(periods, dtype="float64")
    adjusted_close = 100.0 * np.exp(0.0008 * step + 0.02 * np.sin(step / 8.0))
    return pd.DataFrame(
        {
            "ticker": "TEST",
            "open": adjusted_close * (1.0 - 0.002),
            "high": adjusted_close * 1.01,
            "low": adjusted_close * 0.99,
            "close": adjusted_close,
            "adjusted_close": adjusted_close,
            "volume": (1_000_000 + step * 1_000).astype("int64"),
        },
        index=index,
    )


class FeatureConstructionTests(unittest.TestCase):
    def test_target_is_forward_five_day_return(self) -> None:
        market_data = sample_market_data()

        dataset = build_ml_dataset(market_data, horizon=5)

        date = dataset.index[10]
        position = market_data.index.get_loc(date)
        expected = (
            market_data["adjusted_close"].iloc[position + 5]
            / market_data["adjusted_close"].iloc[position]
            - 1.0
        )
        self.assertAlmostEqual(dataset.loc[date, "target_return_5d"], expected, places=12)
        self.assertNotIn("ticker", dataset.columns)
        self.assertEqual(dataset.attrs["horizon_days"], 5)

    def test_point_in_time_fundamentals_are_never_backfilled(self) -> None:
        market_data = sample_market_data()
        first_release = market_data.index[80]
        second_release = market_data.index[150]
        history = pd.DataFrame(
            {
                "pe_ratio": [20.0, 24.0],
                "pb_ratio": [4.0, 5.0],
                "ev_to_ebitda": [12.0, 14.0],
                "roe": [0.20, 0.24],
                "profit_margin": [0.10, 0.12],
                "debt_ratio": [0.40, 0.35],
            },
            index=pd.DatetimeIndex([first_release, second_release]),
        )

        dataset = build_ml_dataset(market_data, fundamental_history=history)

        self.assertGreaterEqual(dataset.index.min(), first_release)
        before_second = dataset.index[
            (dataset.index >= first_release) & (dataset.index < second_release)
        ]
        after_second = dataset.index[dataset.index >= second_release]
        self.assertTrue((dataset.loc[before_second, "fundamental_pe_ratio"] == 20.0).all())
        self.assertTrue((dataset.loc[after_second, "fundamental_pe_ratio"] == 24.0).all())


class ChronologicalSplitTests(unittest.TestCase):
    def test_split_is_chronological_and_purged_at_each_boundary(self) -> None:
        index = pd.bdate_range("2024-01-01", periods=100)
        dataset = pd.DataFrame(
            {"feature": np.arange(100.0), "target_return_5d": np.arange(100.0) / 100.0},
            index=index,
        )
        dataset.attrs["target_column"] = "target_return_5d"

        splits = split_time_series_dataset(dataset, purge_gap=5)

        self.assertEqual(len(splits.X_train), 55)
        self.assertEqual(len(splits.X_validation), 15)
        self.assertEqual(len(splits.X_test), 20)
        self.assertEqual(splits.X_train.index.max(), index[54])
        self.assertEqual(splits.X_validation.index.min(), index[60])
        self.assertEqual(splits.X_validation.index.max(), index[74])
        self.assertEqual(splits.X_test.index.min(), index[80])
        self.assertTrue(splits.X_train.index.max() < splits.X_validation.index.min())
        self.assertTrue(splits.X_validation.index.max() < splits.X_test.index.min())


if __name__ == "__main__":
    unittest.main()
