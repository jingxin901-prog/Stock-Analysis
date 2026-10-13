"""Constrained Markowitz portfolio optimization and efficient-frontier tools."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

import numpy as np
import pandas as pd
from scipy.optimize import OptimizeResult, minimize

DEFAULT_TRADING_DAYS: Final = 252
CovarianceEstimator = Literal["sample", "oas"]


class PortfolioOptimizationError(ValueError):
    """Raised when portfolio inputs or a constrained optimization are invalid."""


@dataclass(frozen=True)
class MarketEstimates:
    """Annualized estimates and covariance diagnostics used by the optimizer."""

    expected_returns: pd.Series
    covariance_matrix: pd.DataFrame
    return_observations: int
    start_date: str
    end_date: str
    periods_per_year: int
    covariance_estimator: CovarianceEstimator
    shrinkage_intensity: float | None
    covariance_condition_number: float
    sample_covariance_condition_number: float


@dataclass(frozen=True)
class CovarianceEstimate:
    """One annualized covariance estimate with stability diagnostics."""

    covariance_matrix: pd.DataFrame
    estimator: CovarianceEstimator
    shrinkage_intensity: float | None
    condition_number: float
    sample_condition_number: float


@dataclass(frozen=True)
class PortfolioResult:
    """Serializable portfolio allocation and performance summary."""

    strategy: str
    weights: dict[str, float]
    cash_weight: float
    expected_return: float
    volatility: float
    sharpe_ratio: float | None
    risk_free_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def prepare_price_matrix(
    market_data: Mapping[str, pd.DataFrame],
    *,
    price_column: str = "adjusted_close",
) -> pd.DataFrame:
    """Inner-align standardized single-ticker frames into a price matrix."""

    if not isinstance(market_data, Mapping) or not market_data:
        raise PortfolioOptimizationError("market_data must contain at least two tickers.")

    series: list[pd.Series] = []
    seen: set[str] = set()
    for ticker, frame in market_data.items():
        symbol = str(ticker).strip().upper()
        if not symbol or symbol in seen:
            raise PortfolioOptimizationError("market_data ticker keys must be unique and nonempty.")
        if not isinstance(frame, pd.DataFrame) or price_column not in frame.columns:
            raise PortfolioOptimizationError(f"Missing {price_column} data for {symbol}.")
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise PortfolioOptimizationError(f"Price data for {symbol} must use a DatetimeIndex.")
        if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise PortfolioOptimizationError(
                f"Price dates for {symbol} must be unique and ascending."
            )

        values = pd.to_numeric(frame[price_column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all() or (values <= 0.0).any():
            raise PortfolioOptimizationError(
                f"Price data for {symbol} must contain finite positive values."
            )
        series.append(values.astype("float64").rename(symbol))
        seen.add(symbol)

    if len(series) < 2:
        raise PortfolioOptimizationError("Portfolio optimization requires at least two tickers.")

    matrix = pd.concat(series, axis=1, join="inner").dropna()
    matrix.index.name = "date"
    if len(matrix) < 3:
        raise PortfolioOptimizationError("At least three aligned price observations are required.")
    return matrix


def estimate_market_inputs(
    price_matrix: pd.DataFrame,
    *,
    periods_per_year: int = DEFAULT_TRADING_DAYS,
    covariance_estimator: CovarianceEstimator = "sample",
) -> MarketEstimates:
    """Estimate arithmetic annual returns and a selected annualized covariance."""

    _validate_price_matrix(price_matrix)
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int):
        raise PortfolioOptimizationError("periods_per_year must be a positive integer.")
    if periods_per_year <= 0:
        raise PortfolioOptimizationError("periods_per_year must be a positive integer.")

    returns = price_matrix / price_matrix.shift(1) - 1.0
    returns = returns.dropna(how="any")
    if len(returns) < 2:
        raise PortfolioOptimizationError("At least two aligned return observations are required.")

    expected_returns = (returns.mean() * periods_per_year).astype("float64")
    covariance = estimate_covariance_matrix(
        returns,
        periods_per_year=periods_per_year,
        estimator=covariance_estimator,
    )

    return MarketEstimates(
        expected_returns=expected_returns,
        covariance_matrix=covariance.covariance_matrix,
        return_observations=len(returns),
        start_date=returns.index.min().date().isoformat(),
        end_date=returns.index.max().date().isoformat(),
        periods_per_year=periods_per_year,
        covariance_estimator=covariance.estimator,
        shrinkage_intensity=covariance.shrinkage_intensity,
        covariance_condition_number=covariance.condition_number,
        sample_covariance_condition_number=covariance.sample_condition_number,
    )


def estimate_covariance_matrix(
    returns: pd.DataFrame,
    *,
    periods_per_year: int = DEFAULT_TRADING_DAYS,
    estimator: CovarianceEstimator = "sample",
) -> CovarianceEstimate:
    """Estimate annualized covariance using sample or OAS shrinkage.

    Oracle Approximating Shrinkage pulls the empirical covariance toward a
    scaled identity matrix. This reduces estimation noise and ill-conditioning
    in small or highly correlated universes without using future data.
    """

    if estimator not in ("sample", "oas"):
        raise PortfolioOptimizationError(
            "covariance_estimator must be either 'sample' or 'oas'."
        )
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int):
        raise PortfolioOptimizationError("periods_per_year must be a positive integer.")
    if periods_per_year <= 0:
        raise PortfolioOptimizationError("periods_per_year must be a positive integer.")
    if not isinstance(returns, pd.DataFrame) or returns.shape[1] < 2 or len(returns) < 2:
        raise PortfolioOptimizationError(
            "returns must contain at least two observations for at least two assets."
        )
    if returns.columns.duplicated().any():
        raise PortfolioOptimizationError("returns asset columns must be unique.")
    numeric = returns.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise PortfolioOptimizationError("returns must contain finite numeric values.")

    sample_daily = numeric.cov(ddof=1).astype("float64")
    sample_daily = (sample_daily + sample_daily.T) / 2.0
    sample_condition_number = _condition_number(sample_daily.to_numpy(dtype="float64"))

    shrinkage_intensity: float | None = None
    if estimator == "sample":
        selected_daily = sample_daily
    else:
        observations = numeric.to_numpy(dtype="float64")
        centered = observations - observations.mean(axis=0, keepdims=True)
        empirical = centered.T @ centered / len(centered)
        asset_count = empirical.shape[0]
        mean_variance = float(np.trace(empirical) / asset_count)
        mean_square = float(np.mean(empirical**2))
        numerator = mean_square + mean_variance**2
        denominator = (len(centered) + 1.0) * (
            mean_square - mean_variance**2 / asset_count
        )
        shrinkage_intensity = (
            1.0
            if denominator <= 1e-30
            else float(np.clip(numerator / denominator, 0.0, 1.0))
        )
        target = np.eye(asset_count, dtype="float64") * mean_variance
        shrunk = (
            (1.0 - shrinkage_intensity) * empirical
            + shrinkage_intensity * target
        )
        selected_daily = pd.DataFrame(
            (shrunk + shrunk.T) / 2.0,
            index=numeric.columns,
            columns=numeric.columns,
            dtype="float64",
        )

    annualized = (selected_daily * periods_per_year).astype("float64")
    annualized = (annualized + annualized.T) / 2.0
    return CovarianceEstimate(
        covariance_matrix=annualized,
        estimator=estimator,
        shrinkage_intensity=shrinkage_intensity,
        condition_number=_condition_number(selected_daily.to_numpy(dtype="float64")),
        sample_condition_number=sample_condition_number,
    )


def _condition_number(covariance: np.ndarray) -> float:
    value = float(np.linalg.cond(covariance))
    return value if math.isfinite(value) else float(np.finfo("float64").max)


def optimize_max_sharpe(
    expected_returns: pd.Series,
    covariance_matrix: pd.DataFrame,
    *,
    risk_free_rate: float = 0.0,
    cash_weight: float = 0.0,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> PortfolioResult:
    """Find the long-only constrained maximum-Sharpe portfolio."""

    tickers, mu, covariance = _validated_optimization_inputs(expected_returns, covariance_matrix)
    bounds, initial_weights = _weight_constraints(
        len(tickers), cash_weight=cash_weight, min_weight=min_weight, max_weight=max_weight
    )
    _validate_risk_free_rate(risk_free_rate)
    risky_weight = 1.0 - cash_weight

    def objective(weights: np.ndarray) -> float:
        portfolio_return, volatility = _portfolio_performance(
            weights, mu, covariance, cash_weight, risk_free_rate
        )
        if volatility <= 1e-15:
            return 1e12
        return -(portfolio_return - risk_free_rate) / volatility

    result = minimize(
        objective,
        initial_weights,
        method="SLSQP",
        bounds=bounds,
        constraints={"type": "eq", "fun": lambda weights: np.sum(weights) - risky_weight},
        options={"ftol": 1e-12, "maxiter": 1_000, "disp": False},
    )
    weights = _validated_solver_result(result, risky_weight, bounds, "maximum Sharpe")
    return _build_result(
        "max_sharpe", tickers, weights, mu, covariance, cash_weight, risk_free_rate
    )


def optimize_minimum_volatility(
    expected_returns: pd.Series,
    covariance_matrix: pd.DataFrame,
    *,
    risk_free_rate: float = 0.0,
    cash_weight: float = 0.0,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
) -> PortfolioResult:
    """Find the long-only constrained global minimum-volatility portfolio."""

    tickers, mu, covariance = _validated_optimization_inputs(expected_returns, covariance_matrix)
    bounds, initial_weights = _weight_constraints(
        len(tickers), cash_weight=cash_weight, min_weight=min_weight, max_weight=max_weight
    )
    _validate_risk_free_rate(risk_free_rate)
    risky_weight = 1.0 - cash_weight

    result = minimize(
        lambda weights: float(weights @ covariance @ weights),
        initial_weights,
        method="SLSQP",
        bounds=bounds,
        constraints={"type": "eq", "fun": lambda weights: np.sum(weights) - risky_weight},
        options={"ftol": 1e-12, "maxiter": 1_000, "disp": False},
    )
    weights = _validated_solver_result(result, risky_weight, bounds, "minimum volatility")
    return _build_result(
        "min_volatility", tickers, weights, mu, covariance, cash_weight, risk_free_rate
    )


def calculate_efficient_frontier(
    expected_returns: pd.Series,
    covariance_matrix: pd.DataFrame,
    *,
    risk_free_rate: float = 0.0,
    cash_weight: float = 0.0,
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    points: int = 30,
) -> pd.DataFrame:
    """Calculate the upper mean-variance frontier under the supplied bounds."""

    if isinstance(points, bool) or not isinstance(points, int) or points < 2:
        raise PortfolioOptimizationError("points must be an integer of at least 2.")

    tickers, mu, covariance = _validated_optimization_inputs(expected_returns, covariance_matrix)
    bounds, initial_weights = _weight_constraints(
        len(tickers), cash_weight=cash_weight, min_weight=min_weight, max_weight=max_weight
    )
    _validate_risk_free_rate(risk_free_rate)
    risky_weight = 1.0 - cash_weight

    min_volatility = optimize_minimum_volatility(
        expected_returns,
        covariance_matrix,
        risk_free_rate=risk_free_rate,
        cash_weight=cash_weight,
        min_weight=min_weight,
        max_weight=max_weight,
    )

    max_return_solution = minimize(
        lambda weights: -float(weights @ mu + cash_weight * risk_free_rate),
        initial_weights,
        method="SLSQP",
        bounds=bounds,
        constraints={"type": "eq", "fun": lambda weights: np.sum(weights) - risky_weight},
        options={"ftol": 1e-12, "maxiter": 1_000, "disp": False},
    )
    max_return_weights = _validated_solver_result(
        max_return_solution, risky_weight, bounds, "maximum return"
    )
    maximum_return = float(max_return_weights @ mu + cash_weight * risk_free_rate)

    if maximum_return - min_volatility.expected_return <= 1e-10:
        raise PortfolioOptimizationError(
            "Expected returns do not provide a nontrivial efficient-frontier range."
        )

    targets = np.linspace(min_volatility.expected_return, maximum_return, points)
    rows: list[dict[str, float]] = []
    previous_weights = np.array(list(min_volatility.weights.values()), dtype="float64")

    for index, target in enumerate(targets):
        if index == 0:
            weights = previous_weights
        elif index == len(targets) - 1:
            weights = max_return_weights
        else:
            constraints = (
                {"type": "eq", "fun": lambda values: np.sum(values) - risky_weight},
                {
                    "type": "eq",
                    "fun": lambda values, target_return=target: (
                        values @ mu + cash_weight * risk_free_rate - target_return
                    ),
                },
            )
            solution = minimize(
                lambda values: float(values @ covariance @ values),
                previous_weights,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"ftol": 1e-12, "maxiter": 1_000, "disp": False},
            )
            weights = _validated_solver_result(
                solution, risky_weight, bounds, f"frontier target {target:.6f}"
            )
            previous_weights = weights

        portfolio_return, volatility = _portfolio_performance(
            weights, mu, covariance, cash_weight, risk_free_rate
        )
        sharpe = None if volatility <= 1e-15 else (portfolio_return - risk_free_rate) / volatility
        row: dict[str, float] = {
            "target_return": float(target),
            "expected_return": portfolio_return,
            "volatility": volatility,
            "sharpe_ratio": float("nan") if sharpe is None else float(sharpe),
            "cash_weight": cash_weight,
        }
        row.update(
            {
                f"weight_{ticker}": float(weight)
                for ticker, weight in zip(tickers, weights, strict=True)
            }
        )
        rows.append(row)

    return pd.DataFrame(rows)


def _validate_price_matrix(price_matrix: pd.DataFrame) -> None:
    if not isinstance(price_matrix, pd.DataFrame) or price_matrix.empty:
        raise PortfolioOptimizationError("price_matrix must be a nonempty DataFrame.")
    if price_matrix.shape[1] < 2:
        raise PortfolioOptimizationError("price_matrix must contain at least two assets.")
    if not isinstance(price_matrix.index, pd.DatetimeIndex):
        raise PortfolioOptimizationError("price_matrix must use a DatetimeIndex.")
    if price_matrix.index.has_duplicates or not price_matrix.index.is_monotonic_increasing:
        raise PortfolioOptimizationError("price_matrix dates must be unique and ascending.")
    if price_matrix.columns.duplicated().any():
        raise PortfolioOptimizationError("price_matrix asset columns must be unique.")
    numeric = price_matrix.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy()).all():
        raise PortfolioOptimizationError("price_matrix must contain finite numeric values.")
    if (numeric <= 0.0).any().any():
        raise PortfolioOptimizationError("price_matrix prices must be strictly positive.")


def _validated_optimization_inputs(
    expected_returns: pd.Series,
    covariance_matrix: pd.DataFrame,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    if not isinstance(expected_returns, pd.Series) or len(expected_returns) < 2:
        raise PortfolioOptimizationError("expected_returns must contain at least two assets.")
    if expected_returns.index.has_duplicates:
        raise PortfolioOptimizationError("expected_returns asset labels must be unique.")
    tickers = [str(ticker) for ticker in expected_returns.index]
    mu = pd.to_numeric(expected_returns, errors="coerce").to_numpy(dtype="float64")
    if not np.isfinite(mu).all():
        raise PortfolioOptimizationError("expected_returns must be finite.")

    if not isinstance(covariance_matrix, pd.DataFrame):
        raise PortfolioOptimizationError("covariance_matrix must be a DataFrame.")
    if set(covariance_matrix.index) != set(expected_returns.index) or set(
        covariance_matrix.columns
    ) != set(expected_returns.index):
        raise PortfolioOptimizationError(
            "covariance_matrix labels must match expected_returns exactly."
        )
    covariance = covariance_matrix.loc[expected_returns.index, expected_returns.index].to_numpy(
        dtype="float64"
    )
    if not np.isfinite(covariance).all() or not np.allclose(covariance, covariance.T, atol=1e-10):
        raise PortfolioOptimizationError("covariance_matrix must be finite and symmetric.")
    eigenvalues = np.linalg.eigvalsh(covariance)
    if float(eigenvalues.min()) < -1e-8:
        raise PortfolioOptimizationError("covariance_matrix must be positive semidefinite.")
    covariance = covariance + np.eye(len(tickers)) * 1e-12
    return tickers, mu, covariance


def _weight_constraints(
    asset_count: int,
    *,
    cash_weight: float,
    min_weight: float,
    max_weight: float,
) -> tuple[list[tuple[float, float]], np.ndarray]:
    for name, value in (
        ("cash_weight", cash_weight),
        ("min_weight", min_weight),
        ("max_weight", max_weight),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise PortfolioOptimizationError(f"{name} must be a finite number.")
    if not 0.0 <= cash_weight < 1.0:
        raise PortfolioOptimizationError("cash_weight must satisfy 0 <= cash_weight < 1.")
    if not 0.0 <= min_weight <= max_weight <= 1.0:
        raise PortfolioOptimizationError("weights must satisfy 0 <= min_weight <= max_weight <= 1.")

    risky_weight = 1.0 - cash_weight
    if asset_count * min_weight > risky_weight + 1e-12:
        raise PortfolioOptimizationError("Minimum weights are infeasible for the risky allocation.")
    if asset_count * max_weight < risky_weight - 1e-12:
        raise PortfolioOptimizationError("Maximum weights are infeasible for the risky allocation.")

    initial_weights = np.full(asset_count, risky_weight / asset_count, dtype="float64")
    bounds = [(float(min_weight), float(max_weight))] * asset_count
    return bounds, initial_weights


def _validate_risk_free_rate(risk_free_rate: float) -> None:
    if (
        isinstance(risk_free_rate, bool)
        or not isinstance(risk_free_rate, (int, float))
        or not math.isfinite(risk_free_rate)
        or risk_free_rate <= -1.0
    ):
        raise PortfolioOptimizationError("risk_free_rate must be finite and greater than -100%.")


def _validated_solver_result(
    result: OptimizeResult,
    required_sum: float,
    bounds: list[tuple[float, float]],
    label: str,
) -> np.ndarray:
    if not result.success:
        raise PortfolioOptimizationError(f"{label} optimization failed: {result.message}")
    weights = np.asarray(result.x, dtype="float64")
    if not np.isfinite(weights).all():
        raise PortfolioOptimizationError(f"{label} optimization returned non-finite weights.")
    if not math.isclose(float(weights.sum()), required_sum, abs_tol=1e-7):
        raise PortfolioOptimizationError(f"{label} optimization violated the weight constraint.")
    for weight, (lower, upper) in zip(weights, bounds, strict=True):
        if weight < lower - 1e-7 or weight > upper + 1e-7:
            raise PortfolioOptimizationError(f"{label} optimization violated an asset bound.")
    return weights


def _portfolio_performance(
    weights: np.ndarray,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    cash_weight: float,
    risk_free_rate: float,
) -> tuple[float, float]:
    portfolio_return = float(weights @ expected_returns + cash_weight * risk_free_rate)
    variance = max(0.0, float(weights @ covariance_matrix @ weights))
    return portfolio_return, math.sqrt(variance)


def _build_result(
    strategy: str,
    tickers: list[str],
    weights: np.ndarray,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    cash_weight: float,
    risk_free_rate: float,
) -> PortfolioResult:
    portfolio_return, volatility = _portfolio_performance(
        weights, expected_returns, covariance_matrix, cash_weight, risk_free_rate
    )
    sharpe = None if volatility <= 1e-15 else (portfolio_return - risk_free_rate) / volatility
    return PortfolioResult(
        strategy=strategy,
        weights={ticker: float(weight) for ticker, weight in zip(tickers, weights, strict=True)},
        cash_weight=float(cash_weight),
        expected_return=portfolio_return,
        volatility=volatility,
        sharpe_ratio=None if sharpe is None else float(sharpe),
        risk_free_rate=float(risk_free_rate),
    )
