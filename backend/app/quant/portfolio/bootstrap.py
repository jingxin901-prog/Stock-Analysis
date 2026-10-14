"""Block-bootstrap uncertainty diagnostics for observed backtest paths."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .optimizer import DEFAULT_TRADING_DAYS, PortfolioOptimizationError


@dataclass(frozen=True)
class BootstrapMetricInterval:
    """Point estimate and percentile interval for one path statistic."""

    estimate: float | None
    lower: float | None
    median: float | None
    upper: float | None


@dataclass(frozen=True)
class BootstrapPathStatistics:
    """Bootstrap summaries for the principal portfolio path statistics."""

    cagr: BootstrapMetricInterval
    annualized_volatility: BootstrapMetricInterval
    sharpe_ratio: BootstrapMetricInterval
    maximum_drawdown: BootstrapMetricInterval


@dataclass(frozen=True)
class BacktestBootstrapUncertainty:
    """Paired block-bootstrap results for a strategy and its benchmark."""

    method: str
    confidence_level: float
    resamples: int
    block_length_days: int
    seed: int
    observations: int
    strategy: BootstrapPathStatistics
    benchmark: BootstrapPathStatistics
    strategy_cagr_above_benchmark_fraction: float


def bootstrap_backtest_uncertainty(
    strategy_values: np.ndarray | list[float],
    benchmark_values: np.ndarray | list[float],
    *,
    risk_free_rate: float = 0.0,
    confidence_level: float = 0.95,
    resamples: int = 1_000,
    block_length_days: int = 21,
    seed: int = 42,
    periods_per_year: int = DEFAULT_TRADING_DAYS,
) -> BacktestBootstrapUncertainty:
    """Estimate sampling uncertainty with a paired circular moving-block bootstrap.

    The same sampled block positions are applied to the strategy and benchmark,
    preserving their contemporaneous dependence. Circular blocks make every
    observed return eligible to begin a block and avoid discarding endpoints.
    """

    strategy = _validated_values("strategy_values", strategy_values)
    benchmark = _validated_values("benchmark_values", benchmark_values)
    if strategy.shape != benchmark.shape:
        raise PortfolioOptimizationError(
            "strategy_values and benchmark_values must have the same length."
        )
    if len(strategy) < 3:
        raise PortfolioOptimizationError("Bootstrap paths require at least three values.")
    if (
        isinstance(risk_free_rate, bool)
        or not isinstance(risk_free_rate, (int, float))
        or not math.isfinite(risk_free_rate)
        or risk_free_rate <= -1.0
    ):
        raise PortfolioOptimizationError(
            "risk_free_rate must be finite and greater than -100%."
        )
    if not 0.0 < confidence_level < 1.0:
        raise PortfolioOptimizationError("confidence_level must be between zero and one.")
    for name, value in (
        ("resamples", resamples),
        ("block_length_days", block_length_days),
        ("periods_per_year", periods_per_year),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PortfolioOptimizationError(f"{name} must be a positive integer.")

    strategy_returns = strategy[1:] / strategy[:-1] - 1.0
    benchmark_returns = benchmark[1:] / benchmark[:-1] - 1.0
    observations = len(strategy_returns)
    effective_block_length = min(block_length_days, observations)
    block_offsets = np.arange(effective_block_length, dtype=np.int64)
    blocks_per_sample = math.ceil(observations / effective_block_length)
    generator = np.random.default_rng(seed)

    strategy_metrics = np.empty((resamples, 4), dtype="float64")
    benchmark_metrics = np.empty((resamples, 4), dtype="float64")
    for sample_index in range(resamples):
        starts = generator.integers(0, observations, size=blocks_per_sample)
        sampled_indices = (
            (starts[:, np.newaxis] + block_offsets) % observations
        ).reshape(-1)[:observations]
        strategy_metrics[sample_index] = _path_statistics(
            strategy_returns[sampled_indices], risk_free_rate, periods_per_year
        )
        benchmark_metrics[sample_index] = _path_statistics(
            benchmark_returns[sampled_indices], risk_free_rate, periods_per_year
        )

    strategy_point = _path_statistics(strategy_returns, risk_free_rate, periods_per_year)
    benchmark_point = _path_statistics(benchmark_returns, risk_free_rate, periods_per_year)
    return BacktestBootstrapUncertainty(
        method="paired_circular_moving_block",
        confidence_level=float(confidence_level),
        resamples=resamples,
        block_length_days=effective_block_length,
        seed=seed,
        observations=observations,
        strategy=_summarize_statistics(strategy_point, strategy_metrics, confidence_level),
        benchmark=_summarize_statistics(benchmark_point, benchmark_metrics, confidence_level),
        strategy_cagr_above_benchmark_fraction=float(
            np.mean(strategy_metrics[:, 0] > benchmark_metrics[:, 0])
        ),
    )


def _validated_values(name: str, values: np.ndarray | list[float]) -> np.ndarray:
    array = np.asarray(values, dtype="float64")
    if array.ndim != 1:
        raise PortfolioOptimizationError(f"{name} must be one-dimensional.")
    if not np.isfinite(array).all() or np.any(array <= 0.0):
        raise PortfolioOptimizationError(f"{name} must contain finite positive values.")
    return array


def _path_statistics(
    returns: np.ndarray, risk_free_rate: float, periods_per_year: int
) -> np.ndarray:
    observations = len(returns)
    log_growth = float(np.log1p(returns).sum())
    cagr = math.expm1(log_growth * periods_per_year / observations)
    standard_deviation = float(np.std(returns, ddof=1))
    annualized_volatility = standard_deviation * math.sqrt(periods_per_year)
    daily_risk_free = math.expm1(math.log1p(risk_free_rate) / periods_per_year)
    sharpe_ratio = (
        math.nan
        if standard_deviation <= 1e-15
        else float(
            (float(np.mean(returns)) - daily_risk_free)
            / standard_deviation
            * math.sqrt(periods_per_year)
        )
    )
    wealth = np.concatenate(([1.0], np.cumprod(1.0 + returns)))
    maximum_drawdown = float(np.min(wealth / np.maximum.accumulate(wealth) - 1.0))
    return np.array(
        [cagr, annualized_volatility, sharpe_ratio, maximum_drawdown], dtype="float64"
    )


def _summarize_statistics(
    point_estimates: np.ndarray,
    bootstrap_statistics: np.ndarray,
    confidence_level: float,
) -> BootstrapPathStatistics:
    intervals = [
        _metric_interval(point_estimates[index], bootstrap_statistics[:, index], confidence_level)
        for index in range(bootstrap_statistics.shape[1])
    ]
    return BootstrapPathStatistics(
        cagr=intervals[0],
        annualized_volatility=intervals[1],
        sharpe_ratio=intervals[2],
        maximum_drawdown=intervals[3],
    )


def _metric_interval(
    estimate: float, values: np.ndarray, confidence_level: float
) -> BootstrapMetricInterval:
    finite_values = values[np.isfinite(values)]
    finite_estimate = float(estimate) if math.isfinite(float(estimate)) else None
    if not len(finite_values):
        return BootstrapMetricInterval(
            estimate=finite_estimate,
            lower=None,
            median=None,
            upper=None,
        )
    tail_probability = (1.0 - confidence_level) / 2.0
    lower, median, upper = np.quantile(
        finite_values, [tail_probability, 0.5, 1.0 - tail_probability]
    )
    return BootstrapMetricInterval(
        estimate=finite_estimate,
        lower=float(lower),
        median=float(median),
        upper=float(upper),
    )
