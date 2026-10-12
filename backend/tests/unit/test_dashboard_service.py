"""Unit tests for dashboard orchestration resilience."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from app.quant.data import EmptyFundamentalDataError, EmptyMarketDataError
from app.quant.portfolio import PortfolioOptimizationError
from app.schemas.dashboard import IndexPoint, MarketInstrument
from app.services.dashboard import (
    PortfolioMarketDataUnavailableError,
    _load_ml_experiment,
    _load_portfolio_market_data,
    _normalize_custom_peers,
    _resolve_backtest_lookback,
    _safe_fundamental_snapshot,
    _safe_load_factor_record,
    get_market_overview,
)


class DashboardServiceTests(unittest.TestCase):
    def test_ml_experiment_uses_deployable_summary_when_artifact_is_absent(self) -> None:
        report = {
            "ticker": "NVDA",
            "experimental_design": {"horizon_days": 5},
            "comparison": [
                {
                    "model": "Linear Regression",
                    "rmse": 0.06,
                    "mae": 0.04,
                    "direction_accuracy": 0.55,
                }
            ],
            "models": {
                "baseline": {
                    "test_start": "2024-01-01",
                    "test_end": "2025-01-01",
                    "test_observations": 250,
                }
            },
        }

        with tempfile.TemporaryDirectory() as temp_directory:
            project_root = Path(temp_directory)
            summary_path = (
                project_root / "backend" / "app" / "research_results" / "ml_nvda_summary.json"
            )
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(json.dumps(report), encoding="utf-8")

            with patch("app.services.dashboard._PROJECT_ROOT", project_root):
                result = _load_ml_experiment("NVDA")

        self.assertEqual(result.status, "available")
        self.assertEqual(result.horizon_days, 5)
        self.assertEqual(result.test_observations, 250)
        self.assertEqual([metric.model for metric in result.models], ["Linear Regression"])

    @patch("app.services.dashboard._cache_get", return_value=None)
    @patch("app.services.dashboard.load_stock_data")
    def test_portfolio_market_data_reports_every_unavailable_symbol(
        self,
        mocked_loader: object,
        mocked_cache_get: object,
    ) -> None:
        del mocked_cache_get

        def load(symbol: str, *, start: str) -> pd.DataFrame:
            del start
            if symbol in {"NVDA", "SPY"}:
                raise EmptyMarketDataError(f"No data for {symbol}")
            return pd.DataFrame({"adjusted_close": [100.0, 101.0]})

        mocked_loader.side_effect = load  # type: ignore[attr-defined]

        with self.assertRaises(PortfolioMarketDataUnavailableError) as raised:
            _load_portfolio_market_data(["AAPL", "NVDA"], "2015-01-01", "SPY")

        self.assertEqual(raised.exception.unavailable_symbols, ("NVDA", "SPY"))
        self.assertEqual(raised.exception.asset_symbols, ("NVDA",))
        self.assertEqual(raised.exception.benchmark_symbol, "SPY")

    @patch("app.services.dashboard._cache_set")
    @patch("app.services.dashboard._cache_get", return_value=None)
    @patch("app.services.dashboard._load_market_instrument")
    def test_market_overview_preserves_available_series(
        self,
        mocked_loader: object,
        mocked_cache_get: object,
        mocked_cache_set: object,
    ) -> None:
        def load(key: str, name: str, symbol: str, start: str) -> MarketInstrument:
            del start
            if key == "sp500":
                raise EmptyMarketDataError("temporary provider gap")
            return MarketInstrument(
                key=key,
                name=name,
                symbol=symbol,
                latest_price=101.0,
                change=1.0,
                change_percent=0.01,
                as_of="2026-10-08",
                history=[IndexPoint(date="2026-10-08", value=101.0)],
            )

        mocked_loader.side_effect = load  # type: ignore[attr-defined]

        response = get_market_overview()

        self.assertEqual(response.status, "partial")
        self.assertEqual([item.key for item in response.instruments], ["nasdaq", "vix", "bitcoin"])
        self.assertEqual([item.symbol for item in response.unavailable_instruments], ["^GSPC"])
        mocked_cache_get.assert_called_once_with("market-overview")  # type: ignore[attr-defined]
        mocked_cache_set.assert_not_called()  # type: ignore[attr-defined]

    @patch("app.services.dashboard._cache_set")
    @patch("app.services.dashboard._cache_get", return_value=None)
    @patch("app.services.dashboard._load_market_instrument")
    def test_market_overview_returns_structured_unavailable_state(
        self,
        mocked_loader: object,
        mocked_cache_get: object,
        mocked_cache_set: object,
    ) -> None:
        del mocked_cache_get
        mocked_loader.side_effect = EmptyMarketDataError("provider offline")  # type: ignore[attr-defined]

        response = get_market_overview()

        self.assertEqual(response.status, "unavailable")
        self.assertEqual(response.source, "unavailable")
        self.assertEqual(response.instruments, [])
        self.assertEqual(len(response.unavailable_instruments), 4)
        mocked_cache_set.assert_not_called()  # type: ignore[attr-defined]

    def test_custom_peers_are_normalized_deduplicated_and_exclude_target(self) -> None:
        peers = _normalize_custom_peers("NVDA", [" aapl ", "NVDA", "msft", "AAPL"])

        self.assertEqual(peers, ("AAPL", "MSFT"))

    def test_custom_peers_require_two_comparators(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            _normalize_custom_peers("NVDA", ["AAPL", "NVDA"])

    @patch("app.services.dashboard.load_fundamental_data")
    def test_unavailable_fundamental_snapshot_is_disclosed(self, mocked_loader: object) -> None:
        mocked_loader.side_effect = EmptyFundamentalDataError("provider gap")  # type: ignore[attr-defined]

        snapshot = _safe_fundamental_snapshot("600519.SS")

        self.assertEqual(snapshot.source, "unavailable")
        self.assertIsNone(snapshot.pe_ratio)

    @patch("app.services.dashboard._load_factor_record")
    def test_unavailable_factor_peer_is_skipped(self, mocked_loader: object) -> None:
        mocked_loader.side_effect = EmptyMarketDataError("temporary provider gap")  # type: ignore[attr-defined]

        self.assertIsNone(_safe_load_factor_record("601318.SS"))

    def test_short_common_history_uses_largest_supported_fallback(self) -> None:
        index = pd.date_range("2025-01-01", periods=252, freq="B")
        prices = pd.DataFrame({"A": range(252), "B": range(252)}, index=index)
        benchmark = pd.Series(range(252), index=index, dtype="float64")

        actual = _resolve_backtest_lookback(prices, benchmark, requested=252)

        self.assertEqual(actual, 126)

    def test_sufficient_common_history_preserves_requested_lookback(self) -> None:
        index = pd.date_range("2024-01-01", periods=400, freq="B")
        prices = pd.DataFrame({"A": range(400), "B": range(400)}, index=index)
        benchmark = pd.Series(range(400), index=index, dtype="float64")

        actual = _resolve_backtest_lookback(prices, benchmark, requested=252)

        self.assertEqual(actual, 252)

    def test_too_little_common_history_remains_explicit(self) -> None:
        index = pd.date_range("2026-01-01", periods=127, freq="B")
        prices = pd.DataFrame({"A": range(127), "B": range(127)}, index=index)
        benchmark = pd.Series(range(127), index=index, dtype="float64")

        with self.assertRaisesRegex(PortfolioOptimizationError, "more than 126"):
            _resolve_backtest_lookback(prices, benchmark, requested=252)


if __name__ == "__main__":
    unittest.main()
