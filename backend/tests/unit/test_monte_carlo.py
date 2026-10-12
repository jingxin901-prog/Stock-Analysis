"""Tests for the reproducible portfolio Monte Carlo simulation."""

from __future__ import annotations

import unittest

import numpy as np

from backend.app.quant.simulation import MonteCarloError, simulate_portfolio_paths


class MonteCarloTests(unittest.TestCase):
    def test_zero_volatility_matches_target_expected_terminal_value(self) -> None:
        result = simulate_portfolio_paths(
            0.10,
            0.0,
            initial_value=100_000.0,
            days=252,
            simulations=100,
            seed=7,
        )

        np.testing.assert_allclose(result.paths[-1], 110_000.0, rtol=1e-12)
        self.assertAlmostEqual(result.average_case, 110_000.0, places=6)
        self.assertEqual(result.probability_of_loss, 0.0)

    def test_fixed_seed_is_reproducible(self) -> None:
        first = simulate_portfolio_paths(0.08, 0.20, days=30, simulations=500, seed=42)
        second = simulate_portfolio_paths(0.08, 0.20, days=30, simulations=500, seed=42)

        np.testing.assert_array_equal(first.paths, second.paths)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_summary_percentiles_are_ordered(self) -> None:
        result = simulate_portfolio_paths(0.08, 0.20, simulations=2_000, seed=3)

        self.assertLess(result.worst_case, result.median_case)
        self.assertLess(result.median_case, result.best_case)
        self.assertGreaterEqual(result.probability_of_loss, 0.0)
        self.assertLessEqual(result.probability_of_loss, 1.0)
        self.assertEqual(result.paths.shape, (253, 2_000))

    def test_invalid_simulation_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(MonteCarloError, "at least 2"):
            simulate_portfolio_paths(0.08, 0.20, simulations=1)


if __name__ == "__main__":
    unittest.main()
