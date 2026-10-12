"""Unit tests for the normalized current fundamental snapshot."""

from __future__ import annotations

import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app.quant.data import (
    EmptyFundamentalDataError,
    FundamentalDataDownloadError,
    load_fundamental_data,
)


class FundamentalLoaderTests(unittest.TestCase):
    def test_maps_yahoo_fields_and_normalizes_debt_to_equity(self) -> None:
        info = {
            "longName": "NVIDIA Corporation",
            "sector": "Technology",
            "industry": "Semiconductors",
            "marketCap": 4_000_000_000_000,
            "trailingPE": "25.5",
            "priceToBook": 12.0,
            "enterpriseToEbitda": 18.25,
            "returnOnEquity": 0.42,
            "profitMargins": 0.31,
            "debtToEquity": 75.0,
        }

        snapshot = load_fundamental_data(" nvda ", info_provider=lambda ticker: info)

        self.assertEqual(snapshot.ticker, "NVDA")
        self.assertEqual(snapshot.company_name, "NVIDIA Corporation")
        self.assertEqual(snapshot.sector, "Technology")
        self.assertEqual(snapshot.industry, "Semiconductors")
        self.assertEqual(snapshot.market_cap, 4_000_000_000_000)
        self.assertEqual(snapshot.pe_ratio, 25.5)
        self.assertEqual(snapshot.pb_ratio, 12.0)
        self.assertEqual(snapshot.ev_to_ebitda, 18.25)
        self.assertEqual(snapshot.roe, 0.42)
        self.assertEqual(snapshot.profit_margin, 0.31)
        self.assertEqual(snapshot.debt_ratio, 0.75)
        self.assertEqual(snapshot.to_dict()["source"], "yfinance")

    def test_missing_and_nonfinite_fields_remain_none(self) -> None:
        info = {"trailingPE": None, "priceToBook": "not available", "returnOnEquity": float("inf")}

        snapshot = load_fundamental_data("AAPL", info_provider=lambda ticker: info)

        self.assertIsNone(snapshot.pe_ratio)
        self.assertIsNone(snapshot.pb_ratio)
        self.assertIsNone(snapshot.ev_to_ebitda)
        self.assertIsNone(snapshot.roe)
        self.assertIsNone(snapshot.debt_ratio)
        self.assertIsNone(snapshot.company_name)
        self.assertIsNone(snapshot.market_cap)

    def test_empty_snapshot_is_rejected(self) -> None:
        with self.assertRaises(EmptyFundamentalDataError):
            load_fundamental_data("AAPL", info_provider=lambda ticker: {})

    def test_provider_failure_is_wrapped(self) -> None:
        def failing_provider(ticker: str) -> dict[str, object]:
            raise ConnectionError("provider unavailable")

        with self.assertRaisesRegex(FundamentalDataDownloadError, "AAPL"):
            load_fundamental_data("AAPL", info_provider=failing_provider)

    def test_provider_failure_uses_last_successful_snapshot(self) -> None:
        info = {
            "longName": "Example Corporation",
            "sector": "Technology",
            "marketCap": 50_000_000_000,
            "trailingPE": 20.0,
        }

        def failing_provider(ticker: str) -> dict[str, object]:
            raise ConnectionError("provider unavailable")

        with (
            TemporaryDirectory() as cache_directory,
            patch.dict(
                os.environ,
                {"QUANTAI_FUNDAMENTAL_CACHE_DIR": cache_directory},
            ),
        ):
            live = load_fundamental_data("AAPL", info_provider=lambda ticker: info, use_cache=True)
            cached = load_fundamental_data("AAPL", info_provider=failing_provider, use_cache=True)

        self.assertEqual(cached.company_name, live.company_name)
        self.assertEqual(cached.market_cap, live.market_cap)
        self.assertEqual(cached.pe_ratio, live.pe_ratio)
        self.assertEqual(cached.retrieved_at_utc, live.retrieved_at_utc)
        self.assertEqual(cached.source, "fundamental-cache")


if __name__ == "__main__":
    unittest.main()
