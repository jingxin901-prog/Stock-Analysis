"""Deterministic tests for constrained Markowitz optimization."""

from __future__ import annotations

import unittest

import pandas as pd

from backend.app.quant.portfolio import (
    PortfolioOptimizationError,
    calculate_efficient_frontier,
    estimate_market_inputs,
    optimize_max_sharpe,
    optimize_minimum_volatility,
    prepare_price_matrix,
)


def analytical_inputs() -> tuple[pd.Series, pd.DataFrame]:
    expected_returns = pd.Series({"A": 0.12, "B": 0.08}, dtype="float64")
    covariance = pd.DataFrame(
        [[0.04, 0.0], [0.0, 0.01]],
        index=["A", "B"],
        columns=["A", "B"],
        dtype="float64",
    )
    return expected_returns, covariance


class MarketEstimateTests(unittest.TestCase):
    def test_price_frames_are_inner_aligned_by_date(self) -> None:
        first = pd.DataFrame(
            {"adjusted_close": [100.0, 101.0, 102.0, 103.0]},
            index=pd.date_range("2024-01-01", periods=4),
        )
        second = pd.DataFrame(
            {"adjusted_close": [50.0, 51.0, 52.0, 53.0]},
            index=pd.date_range("2024-01-02", periods=4),
        )

        actual = prepare_price_matrix({"aaa": first, "bbb": second})

        self.assertEqual(actual.columns.tolist(), ["AAA", "BBB"])
        self.assertEqual(len(actual), 3)
        self.assertEqual(actual.index.min(), pd.Timestamp("2024-01-02"))

    def test_market_estimates_are_annualized_from_daily_returns(self) -> None:
        index = pd.date_range("2024-01-01", periods=4)
        prices = pd.DataFrame(
            {"A": [100.0, 101.0, 102.01, 103.0301], "B": [100.0, 102.0, 104.04, 106.1208]},
            index=index,
        )

        estimates = estimate_market_inputs(prices)

        self.assertAlmostEqual(estimates.expected_returns["A"], 0.01 * 252, places=10)
        self.assertAlmostEqual(estimates.expected_returns["B"], 0.02 * 252, places=10)
        self.assertEqual(estimates.return_observations, 3)


class OptimizationTests(unittest.TestCase):
    def test_minimum_volatility_matches_inverse_variance_solution(self) -> None:
        expected_returns, covariance = analytical_inputs()

        result = optimize_minimum_volatility(expected_returns, covariance)

        self.assertAlmostEqual(result.weights["A"], 0.20, places=5)
        self.assertAlmostEqual(result.weights["B"], 0.80, places=5)
        self.assertAlmostEqual(sum(result.weights.values()), 1.0, places=8)

    def test_maximum_sharpe_matches_tangency_solution(self) -> None:
        expected_returns, covariance = analytical_inputs()

        result = optimize_max_sharpe(expected_returns, covariance, risk_free_rate=0.02)

        self.assertAlmostEqual(result.weights["A"], 2.5 / 8.5, places=4)
        self.assertAlmostEqual(result.weights["B"], 6.0 / 8.5, places=4)
        self.assertGreater(result.sharpe_ratio or 0.0, 0.0)

    def test_fixed_cash_reserve_reduces_risky_weight_sum(self) -> None:
        expected_returns, covariance = analytical_inputs()

        result = optimize_max_sharpe(
            expected_returns,
            covariance,
            risk_free_rate=0.02,
            cash_weight=0.15,
        )

        self.assertAlmostEqual(sum(result.weights.values()), 0.85, places=8)
        self.assertEqual(result.cash_weight, 0.15)

    def test_efficient_frontier_respects_constraints(self) -> None:
        expected_returns, covariance = analytical_inputs()

        frontier = calculate_efficient_frontier(
            expected_returns,
            covariance,
            risk_free_rate=0.02,
            cash_weight=0.10,
            points=8,
        )

        self.assertEqual(len(frontier), 8)
        self.assertTrue(frontier["expected_return"].is_monotonic_increasing)
        self.assertTrue((frontier["volatility"] >= 0.0).all())
        self.assertTrue(((frontier["weight_A"] + frontier["weight_B"]) - 0.90).abs().lt(1e-7).all())

    def test_infeasible_weight_bounds_are_rejected(self) -> None:
        expected_returns, covariance = analytical_inputs()

        with self.assertRaisesRegex(PortfolioOptimizationError, "Maximum weights"):
            optimize_max_sharpe(
                expected_returns,
                covariance,
                cash_weight=0.0,
                max_weight=0.40,
            )


if __name__ == "__main__":
    unittest.main()
