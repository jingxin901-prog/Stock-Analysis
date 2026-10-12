"""Return and risk metrics used by the QuantAI research pipeline."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Final

import pandas as pd

DEFAULT_TRADING_DAYS: Final = 252
DEFAULT_VAR_CONFIDENCE: Final = 0.95


class FinancialMetricError(ValueError):
    """Raised when a financial metric cannot be calculated safely."""


@dataclass(frozen=True)
class FinancialMetrics:
    """Serializable summary of return and risk statistics."""

    ticker: str | None
    start_date: str
    end_date: str
    price_observations: int
    return_observations: int
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float | None
    maximum_drawdown: float
    value_at_risk: float
    var_confidence_level: float
    risk_free_rate: float
    trading_days_per_year: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dictionary."""

        return asdict(self)


def calculate_daily_returns(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
) -> pd.Series:
    """Calculate simple close-to-close daily returns."""

    price_series = _extract_price_series(prices, price_column=price_column)
    returns = price_series / price_series.shift(1) - 1.0
    returns = returns.dropna().astype("float64")
    returns.name = "daily_return"
    if returns.empty:
        raise FinancialMetricError("At least two price observations are required.")
    return returns


def calculate_monthly_returns(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
) -> pd.Series:
    """Calculate month-end to month-end simple returns.

    The first sampled month is omitted because no prior month-end observation is
    present in the requested price window.
    """

    price_series = _extract_price_series(prices, price_column=price_column)
    monthly_prices = price_series.resample("ME").last()
    returns = (monthly_prices / monthly_prices.shift(1) - 1.0).dropna().astype("float64")
    returns.name = "monthly_return"
    if returns.empty:
        raise FinancialMetricError("At least two month-end price observations are required.")
    return returns


def calculate_annual_returns(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
) -> pd.Series:
    """Calculate calendar year-end to year-end simple returns."""

    price_series = _extract_price_series(prices, price_column=price_column)
    annual_prices = price_series.resample("YE").last()
    returns = (annual_prices / annual_prices.shift(1) - 1.0).dropna().astype("float64")
    returns.name = "annual_return"
    if returns.empty:
        raise FinancialMetricError("At least two year-end price observations are required.")
    return returns


def calculate_annualized_return(
    returns: pd.Series,
    *,
    periods_per_year: int = DEFAULT_TRADING_DAYS,
) -> float:
    """Calculate geometric annualized return from periodic simple returns."""

    clean_returns = _validate_returns(returns)
    _validate_periods_per_year(periods_per_year)
    if (clean_returns < -1.0).any():
        raise FinancialMetricError("Simple returns cannot be less than -100%.")

    compounded_growth = float((1.0 + clean_returns).prod())
    if compounded_growth == 0.0:
        return -1.0
    return compounded_growth ** (periods_per_year / len(clean_returns)) - 1.0


def calculate_annualized_volatility(
    returns: pd.Series,
    *,
    periods_per_year: int = DEFAULT_TRADING_DAYS,
) -> float:
    """Calculate sample volatility annualized by the square-root-of-time rule."""

    clean_returns = _validate_returns(returns, minimum_observations=2)
    _validate_periods_per_year(periods_per_year)
    return float(clean_returns.std(ddof=1) * math.sqrt(periods_per_year))


def calculate_sharpe_ratio(
    returns: pd.Series,
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = DEFAULT_TRADING_DAYS,
) -> float | None:
    """Calculate the annualized arithmetic Sharpe ratio.

    ``risk_free_rate`` is an annual effective rate. It is converted to the
    periodic frequency before excess returns are calculated. ``None`` is
    returned when excess-return volatility is zero and the ratio is undefined.
    """

    clean_returns = _validate_returns(returns, minimum_observations=2)
    _validate_periods_per_year(periods_per_year)
    if not isinstance(risk_free_rate, (int, float)) or isinstance(risk_free_rate, bool):
        raise FinancialMetricError("risk_free_rate must be a finite number.")
    if not math.isfinite(risk_free_rate) or risk_free_rate <= -1.0:
        raise FinancialMetricError("risk_free_rate must be finite and greater than -100%.")

    periodic_risk_free_rate = (1.0 + float(risk_free_rate)) ** (1.0 / periods_per_year) - 1.0
    excess_returns = clean_returns - periodic_risk_free_rate
    periodic_volatility = float(excess_returns.std(ddof=1))
    if math.isclose(periodic_volatility, 0.0, abs_tol=1e-15):
        return None
    return float(excess_returns.mean() / periodic_volatility * math.sqrt(periods_per_year))


def calculate_drawdown_series(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
) -> pd.Series:
    """Calculate percentage drawdown from the running price peak."""

    price_series = _extract_price_series(prices, price_column=price_column)
    drawdowns = price_series / price_series.cummax() - 1.0
    drawdowns = drawdowns.astype("float64")
    drawdowns.name = "drawdown"
    return drawdowns


def calculate_maximum_drawdown(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
) -> float:
    """Return the most negative peak-to-trough drawdown."""

    return float(calculate_drawdown_series(prices, price_column=price_column).min())


def calculate_historical_var(
    returns: pd.Series,
    *,
    confidence_level: float = DEFAULT_VAR_CONFIDENCE,
) -> float:
    """Calculate historical Value at Risk as a nonnegative loss magnitude.

    For example, ``0.025`` at 95% confidence means the empirical one-period loss
    threshold is 2.5%. This function does not scale the result across horizons.
    """

    clean_returns = _validate_returns(returns)
    _validate_confidence_level(confidence_level)
    return_quantile = float(clean_returns.quantile(1.0 - confidence_level))
    return max(0.0, -return_quantile)


def calculate_financial_metrics(
    market_data: pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
    risk_free_rate: float = 0.0,
    var_confidence_level: float = DEFAULT_VAR_CONFIDENCE,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS,
) -> FinancialMetrics:
    """Calculate the standard QuantAI return and risk summary."""

    price_series = _extract_price_series(market_data, price_column=price_column)
    daily_returns = calculate_daily_returns(price_series)
    ticker = _extract_single_ticker(market_data)

    return FinancialMetrics(
        ticker=ticker,
        start_date=price_series.index.min().date().isoformat(),
        end_date=price_series.index.max().date().isoformat(),
        price_observations=len(price_series),
        return_observations=len(daily_returns),
        annualized_return=calculate_annualized_return(
            daily_returns, periods_per_year=trading_days_per_year
        ),
        annualized_volatility=calculate_annualized_volatility(
            daily_returns, periods_per_year=trading_days_per_year
        ),
        sharpe_ratio=calculate_sharpe_ratio(
            daily_returns,
            risk_free_rate=risk_free_rate,
            periods_per_year=trading_days_per_year,
        ),
        maximum_drawdown=calculate_maximum_drawdown(price_series),
        value_at_risk=calculate_historical_var(
            daily_returns, confidence_level=var_confidence_level
        ),
        var_confidence_level=var_confidence_level,
        risk_free_rate=float(risk_free_rate),
        trading_days_per_year=trading_days_per_year,
    )


def _extract_price_series(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str,
) -> pd.Series:
    if isinstance(prices, pd.DataFrame):
        if price_column not in prices.columns:
            raise FinancialMetricError(f"Missing required price column: {price_column}.")
        price_series = prices[price_column].copy()
    elif isinstance(prices, pd.Series):
        price_series = prices.copy()
    else:
        raise TypeError("prices must be a pandas Series or DataFrame.")

    if not isinstance(price_series.index, pd.DatetimeIndex):
        raise FinancialMetricError("Price data must use a DatetimeIndex.")
    if price_series.index.has_duplicates:
        raise FinancialMetricError("Price data must not contain duplicate dates.")
    if not price_series.index.is_monotonic_increasing:
        raise FinancialMetricError("Price data must be sorted in ascending date order.")

    numeric_prices = pd.to_numeric(price_series, errors="coerce")
    if numeric_prices.isna().any():
        raise FinancialMetricError("Price data contains missing or nonnumeric values.")
    if not numeric_prices.map(math.isfinite).all():
        raise FinancialMetricError("Price data contains non-finite values.")
    if (numeric_prices <= 0).any():
        raise FinancialMetricError("Price data must be strictly positive.")
    if numeric_prices.empty:
        raise FinancialMetricError("Price data must not be empty.")

    numeric_prices = numeric_prices.astype("float64")
    numeric_prices.name = price_series.name
    return numeric_prices


def _validate_returns(
    returns: pd.Series,
    *,
    minimum_observations: int = 1,
) -> pd.Series:
    if not isinstance(returns, pd.Series):
        raise TypeError("returns must be a pandas Series.")
    numeric_returns = pd.to_numeric(returns, errors="coerce")
    if len(numeric_returns) < minimum_observations:
        raise FinancialMetricError(
            f"At least {minimum_observations} return observations are required."
        )
    if numeric_returns.isna().any() or not numeric_returns.map(math.isfinite).all():
        raise FinancialMetricError("Returns contain missing, nonnumeric, or non-finite values.")
    return numeric_returns.astype("float64")


def _extract_single_ticker(market_data: pd.DataFrame) -> str | None:
    if "ticker" not in market_data.columns:
        return None
    tickers = market_data["ticker"].dropna().astype(str).unique().tolist()
    if len(tickers) > 1:
        raise FinancialMetricError("Financial metrics require data for exactly one ticker.")
    return tickers[0] if tickers else None


def _validate_periods_per_year(periods_per_year: int) -> None:
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int):
        raise FinancialMetricError("periods_per_year must be a positive integer.")
    if periods_per_year <= 0:
        raise FinancialMetricError("periods_per_year must be a positive integer.")


def _validate_confidence_level(confidence_level: float) -> None:
    if isinstance(confidence_level, bool) or not isinstance(confidence_level, (int, float)):
        raise FinancialMetricError("confidence_level must be a number between 0 and 1.")
    if not math.isfinite(confidence_level) or not 0.0 < confidence_level < 1.0:
        raise FinancialMetricError("confidence_level must be strictly between 0 and 1.")
