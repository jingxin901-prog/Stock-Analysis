"""Reproducible geometric-Brownian-motion portfolio simulations."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Final

import numpy as np

DEFAULT_TRADING_DAYS: Final = 252
DEFAULT_SIMULATIONS: Final = 10_000


class MonteCarloError(ValueError):
    """Raised when a portfolio simulation request is invalid."""


@dataclass(frozen=True)
class MonteCarloResult:
    """Simulation paths and a JSON-compatible terminal-value summary."""

    initial_value: float
    days: int
    simulations: int
    expected_annual_return: float
    annual_volatility: float
    seed: int
    worst_case: float
    average_case: float
    median_case: float
    best_case: float
    probability_of_loss: float
    terminal_standard_deviation: float
    lower_percentile: float
    upper_percentile: float
    paths: np.ndarray = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("paths")
        return result


def simulate_portfolio_paths(
    expected_annual_return: float,
    annual_volatility: float,
    *,
    initial_value: float = 100_000.0,
    days: int = DEFAULT_TRADING_DAYS,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = 42,
    lower_percentile: float = 0.05,
    upper_percentile: float = 0.95,
) -> MonteCarloResult:
    """Simulate daily portfolio values under a lognormal GBM assumption.

    The log drift is calibrated so the model's expected one-year terminal value
    equals ``initial_value * (1 + expected_annual_return)``.
    """

    _validate_inputs(
        expected_annual_return=expected_annual_return,
        annual_volatility=annual_volatility,
        initial_value=initial_value,
        days=days,
        simulations=simulations,
        seed=seed,
        lower_percentile=lower_percentile,
        upper_percentile=upper_percentile,
    )

    annual_log_growth = math.log1p(expected_annual_return)
    daily_drift = (annual_log_growth - 0.5 * annual_volatility**2) / days
    daily_volatility = annual_volatility / math.sqrt(days)
    generator = np.random.default_rng(seed)
    shocks = generator.standard_normal((days, simulations))
    daily_log_returns = daily_drift + daily_volatility * shocks
    cumulative_growth = np.exp(np.cumsum(daily_log_returns, axis=0))
    paths = np.vstack(
        [
            np.full((1, simulations), initial_value, dtype="float64"),
            initial_value * cumulative_growth,
        ]
    )
    terminal_values = paths[-1]

    return MonteCarloResult(
        initial_value=float(initial_value),
        days=days,
        simulations=simulations,
        expected_annual_return=float(expected_annual_return),
        annual_volatility=float(annual_volatility),
        seed=seed,
        worst_case=float(np.quantile(terminal_values, lower_percentile)),
        average_case=float(terminal_values.mean()),
        median_case=float(np.median(terminal_values)),
        best_case=float(np.quantile(terminal_values, upper_percentile)),
        probability_of_loss=float(np.mean(terminal_values < initial_value)),
        terminal_standard_deviation=float(terminal_values.std(ddof=1)),
        lower_percentile=float(lower_percentile),
        upper_percentile=float(upper_percentile),
        paths=paths,
    )


def _validate_inputs(**values: Any) -> None:
    expected_return = values["expected_annual_return"]
    volatility = values["annual_volatility"]
    initial_value = values["initial_value"]
    days = values["days"]
    simulations = values["simulations"]
    seed = values["seed"]
    lower = values["lower_percentile"]
    upper = values["upper_percentile"]

    for name, value in (
        ("expected_annual_return", expected_return),
        ("annual_volatility", volatility),
        ("initial_value", initial_value),
        ("lower_percentile", lower),
        ("upper_percentile", upper),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise MonteCarloError(f"{name} must be a finite number.")
    if expected_return <= -1.0:
        raise MonteCarloError("expected_annual_return must be greater than -100%.")
    if volatility < 0.0:
        raise MonteCarloError("annual_volatility must be nonnegative.")
    if initial_value <= 0.0:
        raise MonteCarloError("initial_value must be positive.")
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise MonteCarloError("days must be a positive integer.")
    if isinstance(simulations, bool) or not isinstance(simulations, int) or simulations < 2:
        raise MonteCarloError("simulations must be an integer of at least 2.")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise MonteCarloError("seed must be an integer.")
    if not 0.0 < lower < upper < 1.0:
        raise MonteCarloError("percentiles must satisfy 0 < lower < upper < 1.")
