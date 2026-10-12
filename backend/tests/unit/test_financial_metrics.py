"""Deterministic tests for return and risk metrics."""

from __future__ import annotations

import math
import unittest

import pandas as pd
from pandas.testing import assert_series_equal

from backend.app.quant.metrics import (
    FinancialMetricError,
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


class ReturnMetricTests(unittest.TestCase):
    def test_daily_returns_are_simple_close_to_close_returns(self) -> None:
        prices = pd.Series(
            [100.0, 110.0, 99.0],
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        )

        actual = calculate_daily_returns(prices)

        expected = pd.Series(
            [0.1, -0.1],
            index=pd.to_datetime(["2024-01-03", "2024-01-04"]),
            name="daily_return",
        )
        assert_series_equal(actual, expected)

    def test_monthly_returns_use_month_end_prices(self) -> None:
        prices = pd.Series(
            [100.0, 105.0, 110.0, 99.0],
            index=pd.to_datetime(["2024-01-10", "2024-01-31", "2024-02-29", "2024-03-29"]),
        )

        actual = calculate_monthly_returns(prices)

        expected = pd.Series(
            [110.0 / 105.0 - 1.0, 99.0 / 110.0 - 1.0],
            index=pd.to_datetime(["2024-02-29", "2024-03-31"]),
            name="monthly_return",
        )
        assert_series_equal(actual, expected, check_freq=False)

    def test_annual_returns_use_calendar_year_end_prices(self) -> None:
        prices = pd.Series(
            [100.0, 120.0, 90.0],
            index=pd.to_datetime(["2022-12-30", "2023-12-29", "2024-12-31"]),
        )

        actual = calculate_annual_returns(prices)

        expected = pd.Series(
            [0.2, -0.25],
            index=pd.to_datetime(["2023-12-31", "2024-12-31"]),
            name="annual_return",
        )
        assert_series_equal(actual, expected, check_freq=False)

    def test_annualized_return_uses_geometric_compounding(self) -> None:
        returns = pd.Series([0.001] * 252)

        actual = calculate_annualized_return(returns)

        self.assertAlmostEqual(actual, 1.001**252 - 1.0, places=12)


class RiskMetricTests(unittest.TestCase):
    def test_annualized_volatility_uses_sample_standard_deviation(self) -> None:
        returns = pd.Series([-0.01, 0.01, -0.01, 0.01])

        actual = calculate_annualized_volatility(returns)

        expected = returns.std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(actual, expected, places=12)

    def test_sharpe_ratio_converts_annual_risk_free_rate(self) -> None:
        returns = pd.Series([0.002, -0.001, 0.003, 0.0, 0.001])
        annual_risk_free_rate = 0.04

        actual = calculate_sharpe_ratio(returns, risk_free_rate=annual_risk_free_rate)

        daily_risk_free_rate = (1.0 + annual_risk_free_rate) ** (1.0 / 252) - 1.0
        excess = returns - daily_risk_free_rate
        expected = excess.mean() / excess.std(ddof=1) * math.sqrt(252)
        self.assertIsNotNone(actual)
        self.assertAlmostEqual(actual or 0.0, expected, places=12)

    def test_sharpe_ratio_is_none_when_volatility_is_zero(self) -> None:
        self.assertIsNone(calculate_sharpe_ratio(pd.Series([0.001] * 10)))

    def test_drawdown_and_maximum_drawdown_are_peak_relative(self) -> None:
        prices = pd.Series(
            [100.0, 120.0, 90.0, 108.0, 130.0, 104.0],
            index=pd.date_range("2024-01-01", periods=6),
        )

        drawdowns = calculate_drawdown_series(prices)

        self.assertAlmostEqual(drawdowns.iloc[2], -0.25)
        self.assertAlmostEqual(drawdowns.iloc[-1], -0.20)
        self.assertAlmostEqual(calculate_maximum_drawdown(prices), -0.25)

    def test_historical_var_is_reported_as_positive_loss_magnitude(self) -> None:
        returns = pd.Series([-0.10, -0.05, 0.0, 0.05, 0.10])

        actual = calculate_historical_var(returns, confidence_level=0.80)

        self.assertAlmostEqual(actual, 0.06, places=12)

    def test_invalid_confidence_level_is_rejected(self) -> None:
        with self.assertRaisesRegex(FinancialMetricError, "strictly between"):
            calculate_historical_var(pd.Series([-0.01, 0.01]), confidence_level=1.0)


class FinancialMetricSummaryTests(unittest.TestCase):
    def test_summary_uses_adjusted_close_and_preserves_ticker(self) -> None:
        index = pd.bdate_range("2023-01-02", periods=260)
        adjusted_close = pd.Series(
            [100.0 * (1.0005**day) for day in range(260)],
            index=index,
        )
        market_data = pd.DataFrame(
            {
                "ticker": "TEST",
                "adjusted_close": adjusted_close,
            },
            index=index,
        )

        summary = calculate_financial_metrics(market_data)

        self.assertEqual(summary.ticker, "TEST")
        self.assertEqual(summary.price_observations, 260)
        self.assertEqual(summary.return_observations, 259)
        self.assertAlmostEqual(summary.annualized_return, 1.0005**252 - 1.0, places=12)
        self.assertAlmostEqual(summary.maximum_drawdown, 0.0)
        self.assertIsNone(summary.sharpe_ratio)
        self.assertEqual(summary.to_dict()["ticker"], "TEST")

    def test_duplicate_dates_are_rejected(self) -> None:
        prices = pd.Series(
            [100.0, 101.0],
            index=pd.to_datetime(["2024-01-02", "2024-01-02"]),
        )

        with self.assertRaisesRegex(FinancialMetricError, "duplicate"):
            calculate_daily_returns(prices)

    def test_multiple_tickers_are_rejected(self) -> None:
        frame = pd.DataFrame(
            {
                "ticker": ["AAPL", "MSFT"],
                "adjusted_close": [100.0, 101.0],
            },
            index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
        )

        with self.assertRaisesRegex(FinancialMetricError, "exactly one ticker"):
            calculate_financial_metrics(frame)


if __name__ == "__main__":
    unittest.main()
