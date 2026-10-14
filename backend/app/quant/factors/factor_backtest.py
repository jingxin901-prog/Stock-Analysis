"""Point-in-time walk-forward validation for the price momentum factor."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .factor_model import FactorModelError


@dataclass(frozen=True)
class MomentumValidationPoint:
    """One non-overlapping factor formation and realization period."""

    formation_date: str
    date: str
    rank_ic: float
    top_group_return: float
    bottom_group_return: float
    long_short_spread: float
    gross_value: float
    net_value: float
    equal_weight_value: float
    turnover: float
    transaction_cost: float
    selected_assets: tuple[str, ...]


@dataclass(frozen=True)
class MomentumFactorValidation:
    """Summary of a cross-sectional walk-forward momentum study."""

    start_date: str
    end_date: str
    universe: tuple[str, ...]
    rebalance_periods: int
    lookback_days: tuple[int, ...]
    forward_days: int
    transaction_cost_bps: float
    mean_rank_ic: float
    rank_ic_t_stat: float | None
    positive_ic_fraction: float
    gross_cagr: float
    net_cagr: float
    equal_weight_cagr: float
    top_minus_bottom_annualized_spread: float
    annualized_volatility: float
    sharpe_ratio: float | None
    maximum_drawdown: float
    average_turnover: float
    cumulative_transaction_cost: float
    path: tuple[MomentumValidationPoint, ...]


def run_momentum_factor_validation(
    price_data: Mapping[str, pd.Series | pd.DataFrame],
    *,
    lookback_days: tuple[int, ...] = (63, 126, 252),
    forward_days: int = 21,
    transaction_cost_bps: float = 10.0,
    top_fraction: float = 0.30,
    annualization_days: int = 252,
) -> MomentumFactorValidation:
    """Validate a trailing momentum rank without using future information.

    At each formation date, every lookback return is converted to a
    cross-sectional percentile rank and the ranks are averaged. The strategy
    holds an equal-weighted top group for one non-overlapping forward period.
    Value and quality inputs are deliberately excluded because Yahoo Finance
    does not provide point-in-time historical fundamental snapshots.
    """

    _validate_parameters(
        price_data,
        lookback_days=lookback_days,
        forward_days=forward_days,
        transaction_cost_bps=transaction_cost_bps,
        top_fraction=top_fraction,
        annualization_days=annualization_days,
    )
    prices = _prepare_price_matrix(price_data)
    maximum_lookback = max(lookback_days)
    if len(prices) < maximum_lookback + forward_days + 1:
        raise FactorModelError(
            "Momentum validation requires at least "
            f"{maximum_lookback + forward_days + 1} common price observations."
        )

    period_positions = range(maximum_lookback, len(prices) - forward_days, forward_days)
    points: list[MomentumValidationPoint] = []
    gross_value = 1.0
    net_value = 1.0
    equal_weight_value = 1.0
    bottom_value = 1.0
    current_weights = pd.Series(0.0, index=prices.columns, dtype="float64")
    current_cash_weight = 1.0
    cumulative_cost = 0.0

    for position in period_positions:
        formation_prices = prices.iloc[position]
        component_ranks = []
        for lookback in lookback_days:
            trailing_return = formation_prices / prices.iloc[position - lookback] - 1.0
            component_ranks.append(trailing_return.rank(method="average", pct=True))
        momentum_score = pd.concat(component_ranks, axis=1).mean(axis=1)
        forward_return = prices.iloc[position + forward_days] / formation_prices - 1.0
        rank_ic = float(momentum_score.rank().corr(forward_return.rank()))

        group_size = max(1, math.ceil(len(prices.columns) * top_fraction))
        group_size = min(group_size, len(prices.columns) // 2)
        top_assets = tuple(momentum_score.nlargest(group_size).index.astype(str))
        bottom_assets = tuple(momentum_score.nsmallest(group_size).index.astype(str))

        target_weights = pd.Series(0.0, index=prices.columns, dtype="float64")
        target_weights.loc[list(top_assets)] = 1.0 / group_size
        turnover = 0.5 * (
            float((target_weights - current_weights).abs().sum())
            + abs(0.0 - current_cash_weight)
        )
        cost_rate = turnover * transaction_cost_bps / 10_000.0
        transaction_cost = net_value * cost_rate
        cumulative_cost += transaction_cost

        top_return = float(forward_return.loc[list(top_assets)].mean())
        bottom_return = float(forward_return.loc[list(bottom_assets)].mean())
        equal_return = float(forward_return.mean())
        gross_value *= 1.0 + top_return
        net_value *= (1.0 - cost_rate) * (1.0 + top_return)
        equal_weight_value *= 1.0 + equal_return
        bottom_value *= 1.0 + bottom_return

        post_period_weights = target_weights * (1.0 + forward_return)
        post_period_total = float(post_period_weights.sum())
        current_weights = post_period_weights / post_period_total
        current_cash_weight = 0.0
        points.append(
            MomentumValidationPoint(
                formation_date=prices.index[position].date().isoformat(),
                date=prices.index[position + forward_days].date().isoformat(),
                rank_ic=rank_ic,
                top_group_return=top_return,
                bottom_group_return=bottom_return,
                long_short_spread=top_return - bottom_return,
                gross_value=gross_value,
                net_value=net_value,
                equal_weight_value=equal_weight_value,
                turnover=turnover,
                transaction_cost=transaction_cost,
                selected_assets=top_assets,
            )
        )

    if len(points) < 2:
        raise FactorModelError("Momentum validation requires at least two forward periods.")

    rank_ics = np.asarray([point.rank_ic for point in points], dtype="float64")
    net_returns = np.asarray(
        [
            (point.net_value / (1.0 if index == 0 else points[index - 1].net_value)) - 1.0
            for index, point in enumerate(points)
        ],
        dtype="float64",
    )
    spreads = np.asarray([point.long_short_spread for point in points], dtype="float64")
    periods_per_year = annualization_days / forward_days
    years = len(points) / periods_per_year
    volatility = float(np.std(net_returns, ddof=1) * math.sqrt(periods_per_year))
    annualized_return = float(np.mean(net_returns) * periods_per_year)
    sharpe_ratio = None if volatility <= 0.0 else annualized_return / volatility
    rank_ic_std = float(np.std(rank_ics, ddof=1))
    rank_ic_t_stat = (
        None
        if rank_ic_std <= 0.0
        else float(np.mean(rank_ics) / (rank_ic_std / math.sqrt(len(rank_ics))))
    )

    return MomentumFactorValidation(
        start_date=points[0].formation_date,
        end_date=points[-1].date,
        universe=tuple(prices.columns.astype(str)),
        rebalance_periods=len(points),
        lookback_days=lookback_days,
        forward_days=forward_days,
        transaction_cost_bps=transaction_cost_bps,
        mean_rank_ic=float(np.mean(rank_ics)),
        rank_ic_t_stat=rank_ic_t_stat,
        positive_ic_fraction=float(np.mean(rank_ics > 0.0)),
        gross_cagr=float(gross_value ** (1.0 / years) - 1.0),
        net_cagr=float(net_value ** (1.0 / years) - 1.0),
        equal_weight_cagr=float(equal_weight_value ** (1.0 / years) - 1.0),
        top_minus_bottom_annualized_spread=float(np.mean(spreads) * periods_per_year),
        annualized_volatility=volatility,
        sharpe_ratio=sharpe_ratio,
        maximum_drawdown=_maximum_drawdown([1.0, *[point.net_value for point in points]]),
        average_turnover=float(np.mean([point.turnover for point in points])),
        cumulative_transaction_cost=cumulative_cost,
        path=tuple(points),
    )


def _prepare_price_matrix(
    price_data: Mapping[str, pd.Series | pd.DataFrame],
) -> pd.DataFrame:
    series_by_ticker: dict[str, pd.Series] = {}
    for raw_ticker, values in price_data.items():
        ticker = str(raw_ticker).strip().upper()
        if isinstance(values, pd.DataFrame):
            if "adjusted_close" not in values.columns:
                raise FactorModelError(f"Missing adjusted_close for {ticker}.")
            series = values["adjusted_close"].copy()
        elif isinstance(values, pd.Series):
            series = values.copy()
        else:
            raise TypeError("Each price input must be a pandas Series or DataFrame.")
        if not isinstance(series.index, pd.DatetimeIndex):
            raise FactorModelError("Price histories must use a DatetimeIndex.")
        if series.index.has_duplicates or not series.index.is_monotonic_increasing:
            raise FactorModelError("Price dates must be unique and sorted.")
        series_by_ticker[ticker] = pd.to_numeric(series, errors="coerce")

    prices = pd.concat(series_by_ticker, axis=1, join="inner").dropna()
    if prices.empty or not np.isfinite(prices.to_numpy(dtype="float64")).all():
        raise FactorModelError("Aligned prices must contain finite observations.")
    if (prices <= 0.0).any().any():
        raise FactorModelError("Prices must be strictly positive.")
    return prices.astype("float64")


def _maximum_drawdown(values: list[float]) -> float:
    array = np.asarray(values, dtype="float64")
    running_maximum = np.maximum.accumulate(array)
    return float(np.min(array / running_maximum - 1.0))


def _validate_parameters(
    price_data: Mapping[str, pd.Series | pd.DataFrame],
    *,
    lookback_days: tuple[int, ...],
    forward_days: int,
    transaction_cost_bps: float,
    top_fraction: float,
    annualization_days: int,
) -> None:
    if len(price_data) < 3:
        raise FactorModelError("Momentum validation requires at least three assets.")
    if not lookback_days or any(day <= 0 for day in lookback_days):
        raise FactorModelError("lookback_days must contain positive integers.")
    if len(set(lookback_days)) != len(lookback_days):
        raise FactorModelError("lookback_days must be unique.")
    if forward_days <= 0 or annualization_days <= 0:
        raise FactorModelError("forward_days and annualization_days must be positive.")
    if not math.isfinite(transaction_cost_bps) or transaction_cost_bps < 0.0:
        raise FactorModelError("transaction_cost_bps must be finite and nonnegative.")
    if not 0.0 < top_fraction <= 0.5:
        raise FactorModelError("top_fraction must be between zero and one half.")
