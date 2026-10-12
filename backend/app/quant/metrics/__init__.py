"""Return and risk metrics."""

from .financial_metrics import (
    DEFAULT_TRADING_DAYS,
    DEFAULT_VAR_CONFIDENCE,
    FinancialMetricError,
    FinancialMetrics,
    calculate_annual_returns,
    calculate_annualized_return,
    calculate_annualized_volatility,
    calculate_daily_returns,
    calculate_drawdown_series,
    calculate_financial_metrics,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_monthly_returns,
    calculate_sharpe_ratio,
)

__all__ = [
    "DEFAULT_TRADING_DAYS",
    "DEFAULT_VAR_CONFIDENCE",
    "FinancialMetricError",
    "FinancialMetrics",
    "calculate_annual_returns",
    "calculate_annualized_return",
    "calculate_annualized_volatility",
    "calculate_daily_returns",
    "calculate_drawdown_series",
    "calculate_financial_metrics",
    "calculate_historical_var",
    "calculate_maximum_drawdown",
    "calculate_monthly_returns",
    "calculate_sharpe_ratio",
]
