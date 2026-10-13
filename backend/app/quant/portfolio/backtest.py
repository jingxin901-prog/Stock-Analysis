"""Walk-forward portfolio backtesting with explicit trading frictions."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .optimizer import (
    DEFAULT_TRADING_DAYS,
    CovarianceEstimator,
    PortfolioOptimizationError,
    estimate_covariance_matrix,
    optimize_max_sharpe,
)


@dataclass(frozen=True)
class BacktestStatistics:
    """Summary statistics calculated from an observed wealth path."""

    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float | None
    maximum_drawdown: float


@dataclass(frozen=True)
class BacktestRiskDiagnostics:
    """Downside and benchmark-relative diagnostics for the realized path."""

    downside_deviation: float
    sortino_ratio: float | None
    beta: float | None
    correlation: float | None
    tracking_error: float
    information_ratio: float | None
    longest_drawdown_days: int
    benchmark_longest_drawdown_days: int


@dataclass(frozen=True)
class BacktestPoint:
    """One date on the strategy and benchmark wealth paths."""

    date: str
    strategy_value: float
    benchmark_value: float
    strategy_drawdown: float
    benchmark_drawdown: float
    strategy_rolling_volatility: float | None
    benchmark_rolling_volatility: float | None
    rolling_beta: float | None


@dataclass(frozen=True)
class RebalanceEvent:
    """Auditable record of a walk-forward rebalance decision."""

    date: str
    turnover: float
    transaction_cost: float
    weights: dict[str, float]


@dataclass(frozen=True)
class WalkForwardBacktest:
    """Complete result of a point-in-time rolling optimization study."""

    start_date: str
    end_date: str
    benchmark: str
    lookback_days: int
    rebalance_days: int
    risk_window_days: int
    transaction_cost_bps: float
    covariance_estimator: CovarianceEstimator
    total_transaction_cost: float
    strategy: BacktestStatistics
    benchmark_statistics: BacktestStatistics
    risk_diagnostics: BacktestRiskDiagnostics
    path: list[BacktestPoint]
    rebalances: list[RebalanceEvent]


@dataclass(frozen=True)
class RobustnessScenario:
    """One comparable lookback/rebalance parameter scenario."""

    lookback_days: int
    rebalance_days: int
    cagr: float
    sharpe_ratio: float | None
    maximum_drawdown: float
    excess_cagr: float
    total_transaction_cost: float
    average_turnover: float
    rebalance_count: int


@dataclass(frozen=True)
class BacktestRobustness:
    """Comparable parameter-grid results sharing one evaluation period."""

    start_date: str
    end_date: str
    benchmark: str
    covariance_estimator: CovarianceEstimator
    benchmark_cagr: float
    lookback_options: list[int]
    rebalance_options: list[int]
    median_cagr: float
    median_sharpe_ratio: float | None
    worst_maximum_drawdown: float
    cagr_dispersion: float
    positive_excess_fraction: float
    scenarios: list[RobustnessScenario]


def run_walk_forward_backtest(
    price_matrix: pd.DataFrame,
    benchmark_prices: pd.Series,
    *,
    benchmark: str = "SPY",
    initial_value: float = 100_000.0,
    risk_free_rate: float = 0.0,
    cash_weight: float = 0.0,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    lookback_days: int = 756,
    rebalance_days: int = 63,
    risk_window_days: int = 63,
    transaction_cost_bps: float = 10.0,
    covariance_estimator: CovarianceEstimator = "sample",
    periods_per_year: int = DEFAULT_TRADING_DAYS,
) -> WalkForwardBacktest:
    """Run a rolling maximum-Sharpe study without using future observations.

    At each rebalance, estimates use only the immediately preceding lookback
    window. Target weights are then held without rebalancing until the next
    scheduled date. Proportional trading costs are deducted from wealth.
    """

    _validate_backtest_inputs(
        price_matrix,
        benchmark_prices,
        initial_value=initial_value,
        risk_free_rate=risk_free_rate,
        lookback_days=lookback_days,
        rebalance_days=rebalance_days,
        risk_window_days=risk_window_days,
        transaction_cost_bps=transaction_cost_bps,
        periods_per_year=periods_per_year,
    )
    benchmark_name = str(benchmark).strip().upper()
    if not benchmark_name:
        raise PortfolioOptimizationError("benchmark must be nonempty.")

    combined = pd.concat(
        [price_matrix.astype("float64"), benchmark_prices.rename("__benchmark__")],
        axis=1,
        join="inner",
    ).dropna()
    returns = combined.pct_change(fill_method=None).dropna(how="any")
    if len(returns) <= lookback_days:
        raise PortfolioOptimizationError(
            "The aligned history must contain observations beyond the lookback window."
        )

    tickers = [str(column) for column in price_matrix.columns]
    asset_returns = returns[tickers]
    benchmark_returns = returns["__benchmark__"]
    cash_daily_factor = (1.0 + risk_free_rate) ** (1.0 / periods_per_year)

    base_date = combined.index[lookback_days]
    holdings = np.zeros(len(tickers) + 1, dtype="float64")
    holdings[-1] = float(initial_value)
    benchmark_value = float(initial_value)
    dates: list[pd.Timestamp] = [base_date]
    strategy_values = [float(initial_value)]
    benchmark_values = [float(initial_value)]
    rebalance_events: list[RebalanceEvent] = []
    total_transaction_cost = 0.0

    for rebalance_start in range(lookback_days, len(returns), rebalance_days):
        training = asset_returns.iloc[rebalance_start - lookback_days : rebalance_start]
        expected_returns = training.mean() * periods_per_year
        covariance = estimate_covariance_matrix(
            training,
            periods_per_year=periods_per_year,
            estimator=covariance_estimator,
        ).covariance_matrix
        result = optimize_max_sharpe(
            expected_returns,
            covariance,
            risk_free_rate=risk_free_rate,
            cash_weight=cash_weight,
            min_weight=min_weight,
            max_weight=max_weight,
        )

        target_weights = np.array(
            [*[result.weights[ticker] for ticker in tickers], cash_weight],
            dtype="float64",
        )
        wealth_before_cost = float(holdings.sum())
        current_weights = holdings / wealth_before_cost
        turnover = 0.5 * float(np.abs(target_weights - current_weights).sum())
        transaction_cost = wealth_before_cost * turnover * transaction_cost_bps / 10_000.0
        wealth_after_cost = wealth_before_cost - transaction_cost
        if wealth_after_cost <= 0.0:
            raise PortfolioOptimizationError("Transaction costs exhausted portfolio wealth.")
        holdings = wealth_after_cost * target_weights
        total_transaction_cost += transaction_cost
        event_date = returns.index[rebalance_start]
        event_weights = dict(result.weights)
        event_weights["Cash"] = float(cash_weight)
        rebalance_events.append(
            RebalanceEvent(
                date=event_date.date().isoformat(),
                turnover=turnover,
                transaction_cost=transaction_cost,
                weights=event_weights,
            )
        )

        interval_end = min(rebalance_start + rebalance_days, len(returns))
        for index in range(rebalance_start, interval_end):
            holdings[:-1] *= 1.0 + asset_returns.iloc[index].to_numpy(dtype="float64")
            holdings[-1] *= cash_daily_factor
            benchmark_value *= 1.0 + float(benchmark_returns.iloc[index])
            dates.append(returns.index[index])
            strategy_values.append(float(holdings.sum()))
            benchmark_values.append(float(benchmark_value))

    strategy_series = pd.Series(strategy_values, index=pd.DatetimeIndex(dates), dtype="float64")
    benchmark_series = pd.Series(benchmark_values, index=pd.DatetimeIndex(dates), dtype="float64")
    strategy_drawdown = strategy_series / strategy_series.cummax() - 1.0
    benchmark_drawdown = benchmark_series / benchmark_series.cummax() - 1.0
    strategy_daily_returns = strategy_series.pct_change(fill_method=None)
    benchmark_daily_returns = benchmark_series.pct_change(fill_method=None)
    annualization = math.sqrt(periods_per_year)
    strategy_rolling_volatility = (
        strategy_daily_returns.rolling(risk_window_days, min_periods=risk_window_days).std(ddof=1)
        * annualization
    )
    benchmark_rolling_volatility = (
        benchmark_daily_returns.rolling(risk_window_days, min_periods=risk_window_days).std(ddof=1)
        * annualization
    )
    rolling_benchmark_variance = benchmark_daily_returns.rolling(
        risk_window_days, min_periods=risk_window_days
    ).var(ddof=1)
    rolling_beta = (
        strategy_daily_returns.rolling(risk_window_days, min_periods=risk_window_days).cov(
            benchmark_daily_returns
        )
        / rolling_benchmark_variance
    )

    return WalkForwardBacktest(
        start_date=dates[0].date().isoformat(),
        end_date=dates[-1].date().isoformat(),
        benchmark=benchmark_name,
        lookback_days=lookback_days,
        rebalance_days=rebalance_days,
        risk_window_days=risk_window_days,
        transaction_cost_bps=float(transaction_cost_bps),
        covariance_estimator=covariance_estimator,
        total_transaction_cost=float(total_transaction_cost),
        strategy=_statistics(strategy_series, risk_free_rate, periods_per_year),
        benchmark_statistics=_statistics(benchmark_series, risk_free_rate, periods_per_year),
        risk_diagnostics=_risk_diagnostics(
            strategy_series,
            benchmark_series,
            risk_free_rate,
            periods_per_year,
        ),
        path=[
            BacktestPoint(
                date=date.date().isoformat(),
                strategy_value=float(strategy_series.loc[date]),
                benchmark_value=float(benchmark_series.loc[date]),
                strategy_drawdown=float(strategy_drawdown.loc[date]),
                benchmark_drawdown=float(benchmark_drawdown.loc[date]),
                strategy_rolling_volatility=_finite_or_none(strategy_rolling_volatility.loc[date]),
                benchmark_rolling_volatility=_finite_or_none(
                    benchmark_rolling_volatility.loc[date]
                ),
                rolling_beta=_finite_or_none(rolling_beta.loc[date]),
            )
            for date in strategy_series.index
        ],
        rebalances=rebalance_events,
    )


def run_backtest_robustness(
    price_matrix: pd.DataFrame,
    benchmark_prices: pd.Series,
    *,
    benchmark: str = "SPY",
    initial_value: float = 100_000.0,
    risk_free_rate: float = 0.0,
    cash_weight: float = 0.0,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    lookback_options: tuple[int, ...] = (252, 504, 756),
    rebalance_options: tuple[int, ...] = (21, 63, 126),
    transaction_cost_bps: float = 10.0,
    covariance_estimator: CovarianceEstimator = "sample",
    periods_per_year: int = DEFAULT_TRADING_DAYS,
) -> BacktestRobustness:
    """Compare a parameter grid over one common out-of-sample period."""

    lookbacks = _validated_grid_options("lookback_options", lookback_options)
    rebalances = _validated_grid_options("rebalance_options", rebalance_options)
    benchmark_name = str(benchmark).strip().upper()
    combined = pd.concat(
        [price_matrix.astype("float64"), benchmark_prices.rename("__benchmark__")],
        axis=1,
        join="inner",
    ).dropna()
    maximum_lookback = max(lookbacks)
    if len(combined) <= maximum_lookback + 1:
        raise PortfolioOptimizationError(
            "The aligned history must contain observations beyond the largest lookback."
        )

    tickers = [str(column) for column in price_matrix.columns]
    scenarios: list[RobustnessScenario] = []
    common_start_date: str | None = None
    common_end_date: str | None = None
    benchmark_cagr: float | None = None
    for lookback_days in lookbacks:
        slice_start = maximum_lookback - lookback_days
        scenario_prices = combined[tickers].iloc[slice_start:]
        scenario_benchmark = combined["__benchmark__"].iloc[slice_start:]
        for rebalance_days in rebalances:
            result = run_walk_forward_backtest(
                scenario_prices,
                scenario_benchmark,
                benchmark=benchmark_name,
                initial_value=initial_value,
                risk_free_rate=risk_free_rate,
                cash_weight=cash_weight,
                min_weight=min_weight,
                max_weight=max_weight,
                lookback_days=lookback_days,
                rebalance_days=rebalance_days,
                transaction_cost_bps=transaction_cost_bps,
                covariance_estimator=covariance_estimator,
                periods_per_year=periods_per_year,
            )
            if common_start_date is None:
                common_start_date = result.start_date
                common_end_date = result.end_date
                benchmark_cagr = result.benchmark_statistics.cagr
            elif result.start_date != common_start_date or result.end_date != common_end_date:
                raise PortfolioOptimizationError(
                    "Robustness scenarios did not align to one evaluation period."
                )
            scenarios.append(
                RobustnessScenario(
                    lookback_days=lookback_days,
                    rebalance_days=rebalance_days,
                    cagr=result.strategy.cagr,
                    sharpe_ratio=result.strategy.sharpe_ratio,
                    maximum_drawdown=result.strategy.maximum_drawdown,
                    excess_cagr=result.strategy.cagr - result.benchmark_statistics.cagr,
                    total_transaction_cost=result.total_transaction_cost,
                    average_turnover=float(
                        np.mean([event.turnover for event in result.rebalances])
                    ),
                    rebalance_count=len(result.rebalances),
                )
            )

    cagr_values = np.array([scenario.cagr for scenario in scenarios], dtype="float64")
    sharpe_values = np.array(
        [scenario.sharpe_ratio for scenario in scenarios if scenario.sharpe_ratio is not None],
        dtype="float64",
    )
    return BacktestRobustness(
        start_date=common_start_date or "",
        end_date=common_end_date or "",
        benchmark=benchmark_name,
        covariance_estimator=covariance_estimator,
        benchmark_cagr=float(benchmark_cagr or 0.0),
        lookback_options=lookbacks,
        rebalance_options=rebalances,
        median_cagr=float(np.median(cagr_values)),
        median_sharpe_ratio=(None if not len(sharpe_values) else float(np.median(sharpe_values))),
        worst_maximum_drawdown=float(min(scenario.maximum_drawdown for scenario in scenarios)),
        cagr_dispersion=float(cagr_values.max() - cagr_values.min()),
        positive_excess_fraction=float(
            np.mean([scenario.excess_cagr > 0.0 for scenario in scenarios])
        ),
        scenarios=scenarios,
    )


def _validated_grid_options(name: str, values: tuple[int, ...]) -> list[int]:
    if not 2 <= len(values) <= 5:
        raise PortfolioOptimizationError(f"{name} must contain two to five values.")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
        raise PortfolioOptimizationError(f"{name} must contain positive integers.")
    if len(set(values)) != len(values):
        raise PortfolioOptimizationError(f"{name} values must be unique.")
    return sorted(values)


def _risk_diagnostics(
    strategy_values: pd.Series,
    benchmark_values: pd.Series,
    risk_free_rate: float,
    periods_per_year: int,
) -> BacktestRiskDiagnostics:
    returns = pd.concat(
        [
            strategy_values.pct_change(fill_method=None).rename("strategy"),
            benchmark_values.pct_change(fill_method=None).rename("benchmark"),
        ],
        axis=1,
    ).dropna()
    strategy_returns = returns["strategy"]
    benchmark_returns = returns["benchmark"]
    daily_risk_free = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess_returns = strategy_returns - daily_risk_free
    downside_returns = excess_returns.clip(upper=0.0)
    downside_deviation = float(
        math.sqrt(float((downside_returns**2).mean())) * math.sqrt(periods_per_year)
    )
    sortino = (
        None
        if downside_deviation <= 1e-15
        else float(excess_returns.mean() * periods_per_year / downside_deviation)
    )

    benchmark_variance = float(benchmark_returns.var(ddof=1))
    beta = (
        None
        if benchmark_variance <= 1e-15
        else float(strategy_returns.cov(benchmark_returns) / benchmark_variance)
    )
    correlation_value = float(strategy_returns.corr(benchmark_returns))
    correlation = correlation_value if math.isfinite(correlation_value) else None

    active_returns = strategy_returns - benchmark_returns
    active_standard_deviation = float(active_returns.std(ddof=1))
    tracking_error = active_standard_deviation * math.sqrt(periods_per_year)
    information_ratio = (
        None
        if active_standard_deviation <= 1e-15
        else float(active_returns.mean() / active_standard_deviation * math.sqrt(periods_per_year))
    )
    return BacktestRiskDiagnostics(
        downside_deviation=downside_deviation,
        sortino_ratio=sortino,
        beta=beta,
        correlation=correlation,
        tracking_error=float(tracking_error),
        information_ratio=information_ratio,
        longest_drawdown_days=_longest_drawdown_days(strategy_values),
        benchmark_longest_drawdown_days=_longest_drawdown_days(benchmark_values),
    )


def _longest_drawdown_days(values: pd.Series) -> int:
    below_peak = values < values.cummax()
    longest = 0
    current = 0
    for is_below_peak in below_peak:
        current = current + 1 if bool(is_below_peak) else 0
        longest = max(longest, current)
    return longest


def _finite_or_none(value: float) -> float | None:
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _statistics(
    values: pd.Series, risk_free_rate: float, periods_per_year: int
) -> BacktestStatistics:
    daily_returns = values.pct_change(fill_method=None).dropna()
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    cagr = float(
        (values.iloc[-1] / values.iloc[0]) ** (periods_per_year / len(daily_returns)) - 1.0
    )
    volatility = float(daily_returns.std(ddof=1) * math.sqrt(periods_per_year))
    daily_risk_free = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    standard_deviation = float(daily_returns.std(ddof=1))
    sharpe = (
        None
        if standard_deviation <= 1e-15
        else float(
            (daily_returns.mean() - daily_risk_free)
            / standard_deviation
            * math.sqrt(periods_per_year)
        )
    )
    maximum_drawdown = float((values / values.cummax() - 1.0).min())
    return BacktestStatistics(
        total_return=total_return,
        cagr=cagr,
        annualized_volatility=volatility,
        sharpe_ratio=sharpe,
        maximum_drawdown=maximum_drawdown,
    )


def _validate_backtest_inputs(
    price_matrix: pd.DataFrame,
    benchmark_prices: pd.Series,
    *,
    initial_value: float,
    risk_free_rate: float,
    lookback_days: int,
    rebalance_days: int,
    risk_window_days: int,
    transaction_cost_bps: float,
    periods_per_year: int,
) -> None:
    if not isinstance(price_matrix, pd.DataFrame) or price_matrix.shape[1] < 2:
        raise PortfolioOptimizationError("price_matrix must contain at least two assets.")
    if not isinstance(price_matrix.index, pd.DatetimeIndex):
        raise PortfolioOptimizationError("price_matrix must use a DatetimeIndex.")
    if not isinstance(benchmark_prices, pd.Series) or not isinstance(
        benchmark_prices.index, pd.DatetimeIndex
    ):
        raise PortfolioOptimizationError("benchmark_prices must be a dated Series.")
    if price_matrix.index.has_duplicates or not price_matrix.index.is_monotonic_increasing:
        raise PortfolioOptimizationError("price_matrix dates must be unique and ascending.")
    if benchmark_prices.index.has_duplicates or not benchmark_prices.index.is_monotonic_increasing:
        raise PortfolioOptimizationError("benchmark dates must be unique and ascending.")
    numeric_prices = price_matrix.apply(pd.to_numeric, errors="coerce")
    numeric_benchmark = pd.to_numeric(benchmark_prices, errors="coerce")
    if (
        numeric_prices.isna().any().any()
        or numeric_benchmark.isna().any()
        or not np.isfinite(numeric_prices.to_numpy()).all()
        or not np.isfinite(numeric_benchmark.to_numpy()).all()
        or (numeric_prices <= 0.0).any().any()
        or (numeric_benchmark <= 0.0).any()
    ):
        raise PortfolioOptimizationError("Backtest prices must be finite and positive.")
    for name, value in (
        ("initial_value", initial_value),
        ("risk_free_rate", risk_free_rate),
        ("transaction_cost_bps", transaction_cost_bps),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise PortfolioOptimizationError(f"{name} must be a finite number.")
    if initial_value <= 0.0:
        raise PortfolioOptimizationError("initial_value must be positive.")
    if risk_free_rate <= -1.0:
        raise PortfolioOptimizationError("risk_free_rate must be greater than -100%.")
    if not 0.0 <= transaction_cost_bps <= 10_000.0:
        raise PortfolioOptimizationError("transaction_cost_bps must be between 0 and 10000.")
    for name, value in (
        ("lookback_days", lookback_days),
        ("rebalance_days", rebalance_days),
        ("risk_window_days", risk_window_days),
        ("periods_per_year", periods_per_year),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PortfolioOptimizationError(f"{name} must be a positive integer.")
