"""Tests for paired block-bootstrap backtest uncertainty."""

from __future__ import annotations

import numpy as np
import pytest
from app.quant.portfolio import PortfolioOptimizationError, bootstrap_backtest_uncertainty


def _wealth_path(returns: np.ndarray, initial_value: float = 100_000.0) -> np.ndarray:
    return initial_value * np.concatenate(([1.0], np.cumprod(1.0 + returns)))


def test_bootstrap_is_reproducible_and_orders_percentile_intervals() -> None:
    generator = np.random.default_rng(7)
    benchmark_returns = generator.normal(0.00035, 0.009, size=504)
    strategy_returns = 0.00015 + 0.72 * benchmark_returns + generator.normal(
        0.0, 0.004, size=504
    )
    strategy = _wealth_path(strategy_returns)
    benchmark = _wealth_path(benchmark_returns)

    first = bootstrap_backtest_uncertainty(
        strategy,
        benchmark,
        resamples=250,
        block_length_days=21,
        seed=19,
    )
    second = bootstrap_backtest_uncertainty(
        strategy,
        benchmark,
        resamples=250,
        block_length_days=21,
        seed=19,
    )

    assert first == second
    assert first.method == "paired_circular_moving_block"
    assert first.observations == 504
    assert 0.0 <= first.strategy_cagr_above_benchmark_fraction <= 1.0
    for summary in (first.strategy, first.benchmark):
        for interval in (
            summary.cagr,
            summary.annualized_volatility,
            summary.sharpe_ratio,
            summary.maximum_drawdown,
        ):
            assert interval.lower is not None
            assert interval.median is not None
            assert interval.upper is not None
            assert interval.lower <= interval.median <= interval.upper


def test_paired_bootstrap_preserves_identical_strategy_benchmark_comparison() -> None:
    returns = np.tile(np.array([0.012, -0.006, 0.004, -0.002]), 80)
    values = _wealth_path(returns)

    result = bootstrap_backtest_uncertainty(
        values,
        values,
        resamples=150,
        block_length_days=17,
        seed=3,
    )

    assert result.strategy == result.benchmark
    assert result.strategy_cagr_above_benchmark_fraction == 0.0


def test_bootstrap_reports_missing_sharpe_for_constant_path() -> None:
    strategy = _wealth_path(np.full(80, 0.001))
    benchmark = _wealth_path(np.full(80, 0.0005))

    result = bootstrap_backtest_uncertainty(
        strategy,
        benchmark,
        resamples=100,
        block_length_days=21,
    )

    assert result.strategy.sharpe_ratio.estimate is None
    assert result.strategy.sharpe_ratio.lower is None
    assert result.strategy.cagr.lower == pytest.approx(result.strategy.cagr.upper)


def test_bootstrap_rejects_misaligned_paths() -> None:
    with pytest.raises(PortfolioOptimizationError, match="same length"):
        bootstrap_backtest_uncertainty([100.0, 101.0, 102.0], [100.0, 101.0])
