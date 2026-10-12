"""Deterministic tests for the walk-forward portfolio study."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from backend.app.quant.portfolio import (
    run_backtest_robustness,
    run_walk_forward_backtest,
)


def synthetic_market() -> tuple[pd.DataFrame, pd.Series, np.ndarray]:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2020-01-01", periods=520)
    returns = np.column_stack(
        [
            rng.normal(0.00055, 0.011, len(dates)),
            rng.normal(0.00030, 0.007, len(dates)),
        ]
    )
    benchmark_returns = rng.normal(0.00038, 0.009, len(dates))
    prices = pd.DataFrame(
        100.0 * np.cumprod(1.0 + returns, axis=0),
        index=dates,
        columns=["AAA", "BBB"],
    )
    benchmark = pd.Series(
        100.0 * np.cumprod(1.0 + benchmark_returns),
        index=dates,
        name="SPY",
    )
    return prices, benchmark, returns


class WalkForwardBacktestTests(unittest.TestCase):
    def test_result_is_dated_and_auditable(self) -> None:
        prices, benchmark, _ = synthetic_market()

        result = run_walk_forward_backtest(
            prices,
            benchmark,
            cash_weight=0.10,
            max_weight=0.80,
            lookback_days=126,
            rebalance_days=63,
            risk_window_days=42,
            transaction_cost_bps=10.0,
        )

        self.assertGreater(len(result.path), 300)
        self.assertGreater(len(result.rebalances), 1)
        self.assertEqual(result.path[0].strategy_value, 100_000.0)
        self.assertEqual(result.path[0].benchmark_value, 100_000.0)
        self.assertAlmostEqual(sum(result.rebalances[0].weights.values()), 1.0, places=7)
        self.assertTrue(math_is_finite(result.strategy.cagr))
        self.assertEqual(result.risk_window_days, 42)
        self.assertTrue(math_is_finite(result.risk_diagnostics.downside_deviation))
        self.assertTrue(math_is_finite(result.risk_diagnostics.tracking_error))
        self.assertIsNotNone(result.risk_diagnostics.beta)
        self.assertGreaterEqual(result.risk_diagnostics.longest_drawdown_days, 0)
        self.assertIsNotNone(result.path[-1].strategy_rolling_volatility)
        self.assertIsNotNone(result.path[-1].benchmark_rolling_volatility)
        self.assertIsNotNone(result.path[-1].rolling_beta)

        realized = (
            pd.DataFrame(
                {
                    "strategy": [point.strategy_value for point in result.path],
                    "benchmark": [point.benchmark_value for point in result.path],
                }
            )
            .pct_change(fill_method=None)
            .dropna()
        )
        expected_beta = realized["strategy"].cov(realized["benchmark"]) / realized["benchmark"].var(
            ddof=1
        )
        expected_tracking_error = (realized["strategy"] - realized["benchmark"]).std(
            ddof=1
        ) * np.sqrt(252)
        self.assertAlmostEqual(result.risk_diagnostics.beta or 0.0, expected_beta)
        self.assertAlmostEqual(
            result.risk_diagnostics.tracking_error,
            expected_tracking_error,
        )

    def test_first_rebalance_does_not_use_future_returns(self) -> None:
        prices, benchmark, returns = synthetic_market()
        altered_returns = returns.copy()
        altered_returns[127:, 0] = -altered_returns[127:, 0]
        altered_prices = pd.DataFrame(
            100.0 * np.cumprod(1.0 + altered_returns, axis=0),
            index=prices.index,
            columns=prices.columns,
        )

        baseline = run_walk_forward_backtest(
            prices,
            benchmark,
            cash_weight=0.10,
            max_weight=0.80,
            lookback_days=126,
            rebalance_days=63,
        )
        altered = run_walk_forward_backtest(
            altered_prices,
            benchmark,
            cash_weight=0.10,
            max_weight=0.80,
            lookback_days=126,
            rebalance_days=63,
        )

        self.assertEqual(
            baseline.rebalances[0].weights,
            altered.rebalances[0].weights,
        )

    def test_transaction_costs_reduce_terminal_wealth(self) -> None:
        prices, benchmark, _ = synthetic_market()

        without_costs = run_walk_forward_backtest(
            prices,
            benchmark,
            cash_weight=0.10,
            max_weight=0.80,
            lookback_days=126,
            rebalance_days=42,
            transaction_cost_bps=0.0,
        )
        with_costs = run_walk_forward_backtest(
            prices,
            benchmark,
            cash_weight=0.10,
            max_weight=0.80,
            lookback_days=126,
            rebalance_days=42,
            transaction_cost_bps=100.0,
        )

        self.assertGreater(with_costs.total_transaction_cost, 0.0)
        self.assertLess(
            with_costs.path[-1].strategy_value,
            without_costs.path[-1].strategy_value,
        )

    def test_robustness_grid_uses_one_common_evaluation_period(self) -> None:
        prices, benchmark, _ = synthetic_market()

        result = run_backtest_robustness(
            prices,
            benchmark,
            cash_weight=0.10,
            max_weight=0.80,
            lookback_options=(63, 126),
            rebalance_options=(21, 63),
            transaction_cost_bps=10.0,
        )

        self.assertEqual(len(result.scenarios), 4)
        self.assertEqual(result.start_date, prices.index[126].date().isoformat())
        self.assertEqual(result.lookback_options, [63, 126])
        self.assertEqual(result.rebalance_options, [21, 63])
        self.assertGreaterEqual(result.positive_excess_fraction, 0.0)
        self.assertLessEqual(result.positive_excess_fraction, 1.0)
        self.assertGreaterEqual(result.cagr_dispersion, 0.0)
        self.assertTrue(all(scenario.rebalance_count > 0 for scenario in result.scenarios))


def math_is_finite(value: float) -> bool:
    return bool(np.isfinite(value))


if __name__ == "__main__":
    unittest.main()
