"""Deterministic tests for factor construction and cross-sectional scoring."""

from __future__ import annotations

import unittest

import pandas as pd

from backend.app.quant.data import FundamentalSnapshot
from backend.app.quant.factors import (
    FactorModelError,
    build_factor_record,
    calculate_momentum_factors,
    score_factor_universe,
)


def ordered_factor_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "pe_ratio": 10.0,
                "pb_ratio": 1.0,
                "ev_to_ebitda": 5.0,
                "momentum_3m": 0.30,
                "momentum_6m": 0.40,
                "momentum_12m": 0.50,
                "roe": 0.30,
                "profit_margin": 0.20,
                "debt_ratio": 0.20,
            },
            {
                "ticker": "BBB",
                "pe_ratio": 20.0,
                "pb_ratio": 2.0,
                "ev_to_ebitda": 10.0,
                "momentum_3m": 0.20,
                "momentum_6m": 0.30,
                "momentum_12m": 0.40,
                "roe": 0.20,
                "profit_margin": 0.15,
                "debt_ratio": 0.40,
            },
            {
                "ticker": "CCC",
                "pe_ratio": 30.0,
                "pb_ratio": 3.0,
                "ev_to_ebitda": 15.0,
                "momentum_3m": 0.10,
                "momentum_6m": 0.20,
                "momentum_12m": 0.30,
                "roe": 0.10,
                "profit_margin": 0.10,
                "debt_ratio": 0.60,
            },
        ]
    )


class MomentumFactorTests(unittest.TestCase):
    def test_momentum_uses_calendar_month_lookbacks(self) -> None:
        prices = pd.Series(
            [100.0, 110.0, 120.0, 160.0],
            index=pd.to_datetime(["2023-01-31", "2023-07-31", "2023-10-31", "2024-01-31"]),
        )

        actual = calculate_momentum_factors(prices)

        self.assertAlmostEqual(actual["momentum_3m"] or 0.0, 160.0 / 120.0 - 1.0)
        self.assertAlmostEqual(actual["momentum_6m"] or 0.0, 160.0 / 110.0 - 1.0)
        self.assertAlmostEqual(actual["momentum_12m"] or 0.0, 160.0 / 100.0 - 1.0)

    def test_insufficient_history_returns_none_for_unavailable_horizon(self) -> None:
        prices = pd.Series(
            [100.0, 110.0, 120.0],
            index=pd.to_datetime(["2023-07-31", "2023-10-31", "2024-01-31"]),
        )

        actual = calculate_momentum_factors(prices)

        self.assertIsNone(actual["momentum_12m"])
        self.assertIsNotNone(actual["momentum_3m"])

    def test_factor_record_combines_snapshot_and_momentum(self) -> None:
        snapshot = FundamentalSnapshot(
            ticker="TEST",
            retrieved_at_utc="2026-09-29T00:00:00+00:00",
            pe_ratio=20.0,
            pb_ratio=5.0,
            ev_to_ebitda=15.0,
            roe=0.25,
            profit_margin=0.18,
            debt_ratio=0.40,
        )
        prices = pd.Series(
            [100.0, 120.0],
            index=pd.to_datetime(["2023-01-31", "2024-01-31"]),
        )

        record = build_factor_record(snapshot, prices)

        self.assertEqual(record["ticker"], "TEST")
        self.assertEqual(record["pe_ratio"], 20.0)
        self.assertAlmostEqual(float(record["momentum_12m"] or 0.0), 0.20)


class FactorScoringTests(unittest.TestCase):
    def test_scores_ordered_cross_section_from_zero_to_one_hundred(self) -> None:
        actual = score_factor_universe(ordered_factor_frame())

        self.assertEqual(actual["ticker"].tolist(), ["AAA", "BBB", "CCC"])
        self.assertEqual(actual["rank"].tolist(), [1, 2, 3])
        self.assertEqual(actual["value_score"].tolist(), [100.0, 50.0, 0.0])
        self.assertEqual(actual["momentum_score"].tolist(), [100.0, 50.0, 0.0])
        self.assertEqual(actual["quality_score"].tolist(), [100.0, 50.0, 0.0])
        self.assertEqual(actual["quant_score"].tolist(), [100.0, 50.0, 0.0])
        self.assertTrue(actual["data_coverage"].eq(1.0).all())

    def test_missing_and_invalid_inputs_receive_neutral_score_and_reduce_coverage(self) -> None:
        frame = ordered_factor_frame()
        frame.loc[0, "pe_ratio"] = None
        frame.loc[1, "debt_ratio"] = -0.5

        actual = score_factor_universe(frame).set_index("ticker")

        self.assertEqual(actual.loc["AAA", "pe_ratio_score"], 50.0)
        self.assertEqual(actual.loc["BBB", "debt_ratio_score"], 50.0)
        self.assertAlmostEqual(actual.loc["AAA", "data_coverage"], 8.0 / 9.0, places=4)
        self.assertAlmostEqual(actual.loc["BBB", "data_coverage"], 8.0 / 9.0, places=4)

    def test_zero_debt_ratio_is_valid_and_scores_as_low_leverage(self) -> None:
        frame = ordered_factor_frame()
        frame.loc[0, "debt_ratio"] = 0.0

        actual = score_factor_universe(frame).set_index("ticker")

        self.assertEqual(actual.loc["AAA", "debt_ratio_score"], 100.0)
        self.assertEqual(actual.loc["AAA", "quality_coverage"], 1.0)

    def test_duplicate_tickers_are_rejected(self) -> None:
        frame = ordered_factor_frame()
        frame.loc[1, "ticker"] = "AAA"

        with self.assertRaisesRegex(FactorModelError, "one row per ticker"):
            score_factor_universe(frame)


if __name__ == "__main__":
    unittest.main()
