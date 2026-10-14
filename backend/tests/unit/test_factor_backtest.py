"""Deterministic tests for point-in-time momentum factor validation."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backend.app.quant.factors import FactorModelError, run_momentum_factor_validation


def trending_price_histories(observations: int = 420) -> dict[str, pd.Series]:
    dates = pd.bdate_range("2020-01-01", periods=observations)
    return {
        ticker: pd.Series(
            100.0 * np.power(1.0 + daily_return, np.arange(observations)),
            index=dates,
        )
        for ticker, daily_return in {
            "AAA": 0.0012,
            "BBB": 0.0008,
            "CCC": 0.0003,
            "DDD": -0.0002,
        }.items()
    }


class MomentumFactorValidationTests(unittest.TestCase):
    def test_walk_forward_ranks_predict_continuing_synthetic_trends(self) -> None:
        result = run_momentum_factor_validation(
            trending_price_histories(), transaction_cost_bps=0.0
        )

        self.assertGreater(result.rebalance_periods, 5)
        self.assertAlmostEqual(result.mean_rank_ic, 1.0)
        self.assertAlmostEqual(result.positive_ic_fraction, 1.0)
        self.assertGreater(result.top_minus_bottom_annualized_spread, 0.0)
        self.assertGreater(result.net_cagr, result.equal_weight_cagr)
        self.assertEqual(result.net_cagr, result.gross_cagr)
        self.assertEqual(result.path[0].formation_date, "2020-12-18")
        self.assertEqual(result.path[0].selected_assets, ("AAA", "BBB"))

    def test_transaction_costs_reduce_net_performance(self) -> None:
        result = run_momentum_factor_validation(
            trending_price_histories(), transaction_cost_bps=25.0
        )

        self.assertLess(result.net_cagr, result.gross_cagr)
        self.assertGreater(result.average_turnover, 0.0)
        self.assertGreater(result.cumulative_transaction_cost, 0.0)
        self.assertAlmostEqual(result.path[0].turnover, 1.0)

    def test_requires_three_assets_and_sufficient_common_history(self) -> None:
        histories = trending_price_histories(observations=200)
        with self.assertRaisesRegex(FactorModelError, "at least three"):
            run_momentum_factor_validation(dict(list(histories.items())[:2]))
        with self.assertRaisesRegex(FactorModelError, "common price observations"):
            run_momentum_factor_validation(histories)


if __name__ == "__main__":
    unittest.main()
