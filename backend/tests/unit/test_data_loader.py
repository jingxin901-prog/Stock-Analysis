"""Unit tests for the standardized historical market-data loader."""

from __future__ import annotations

import os
import unittest
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import call, patch

import pandas as pd
from pandas.testing import assert_frame_equal

from backend.app.quant.data.data_loader import (
    EmptyMarketDataError,
    MarketDataDownloadError,
    MarketDataSchemaError,
    load_stock_data,
)


def sample_provider_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [187.15, "185.64", 184.22],
            "High": [188.44, "187.05", 186.40],
            "Low": [185.82, "184.10", 183.92],
            "Close": [187.58, "186.19", 185.10],
            "Adj Close": [186.81, "185.42", 184.34],
            "Volume": [58_412_300, "61_235_100", 55_900_000],
        },
        index=pd.to_datetime(["2024-01-04", "2024-01-03", "2024-01-03"], utc=True),
    )


class RecordingDownloader:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.ticker: str | None = None
        self.kwargs: dict[str, Any] = {}

    def __call__(self, ticker: str, **kwargs: Any) -> pd.DataFrame:
        self.ticker = ticker
        self.kwargs = kwargs
        return self.frame.copy()


class DataLoaderTests(unittest.TestCase):
    def test_returns_standardized_sorted_duplicate_free_frame(self) -> None:
        downloader = RecordingDownloader(sample_provider_frame())

        actual = load_stock_data(" aapl ", downloader=downloader)

        expected = pd.DataFrame(
            {
                "ticker": ["AAPL", "AAPL"],
                "open": [184.22, 187.15],
                "high": [186.40, 188.44],
                "low": [183.92, 185.82],
                "close": [185.10, 187.58],
                "adjusted_close": [184.34, 186.81],
                "volume": [55_900_000, 58_412_300],
            },
            index=pd.DatetimeIndex(["2024-01-03", "2024-01-04"], name="date"),
        )
        assert_frame_equal(actual, expected)
        self.assertEqual(downloader.kwargs["start"], "2015-01-01")
        self.assertIsNone(downloader.kwargs["end"])
        self.assertEqual(actual.attrs["rows_received"], 3)
        self.assertEqual(actual.attrs["rows_returned"], 2)

    def test_passes_explicit_research_conventions_to_provider(self) -> None:
        downloader = RecordingDownloader(sample_provider_frame())

        load_stock_data(
            "MSFT",
            start="2020-01-02",
            end="2024-01-05",
            timeout=12,
            downloader=downloader,
        )

        self.assertEqual(downloader.ticker, "MSFT")
        self.assertEqual(downloader.kwargs["start"], "2020-01-02")
        self.assertEqual(downloader.kwargs["end"], "2024-01-05")
        self.assertEqual(downloader.kwargs["interval"], "1d")
        self.assertFalse(downloader.kwargs["auto_adjust"])
        self.assertFalse(downloader.kwargs["actions"])
        self.assertFalse(downloader.kwargs["progress"])
        self.assertFalse(downloader.kwargs["threads"])
        self.assertTrue(downloader.kwargs["ignore_tz"])
        self.assertFalse(downloader.kwargs["multi_level_index"])
        self.assertEqual(downloader.kwargs["timeout"], 12.0)

    def test_accepts_single_ticker_multi_index_columns(self) -> None:
        frame = sample_provider_frame()
        frame.columns = pd.MultiIndex.from_tuples(
            [(column, "AAPL") for column in frame.columns],
            names=["Price", "Ticker"],
        )

        actual = load_stock_data("AAPL", downloader=RecordingDownloader(frame))

        self.assertEqual(
            tuple(actual.columns),
            (
                "ticker",
                "open",
                "high",
                "low",
                "close",
                "adjusted_close",
                "volume",
            ),
        )

    def test_rejects_invalid_ticker_before_download(self) -> None:
        downloader = RecordingDownloader(sample_provider_frame())

        with self.assertRaisesRegex(ValueError, "unsupported characters"):
            load_stock_data("AAPL;DROP TABLE", downloader=downloader)

        self.assertIsNone(downloader.ticker)

    def test_rejects_invalid_date_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "earlier than"):
            load_stock_data(
                "AAPL",
                start="2024-01-05",
                end="2024-01-05",
                downloader=RecordingDownloader(sample_provider_frame()),
            )

    def test_raises_for_empty_provider_response(self) -> None:
        with self.assertRaises(EmptyMarketDataError):
            load_stock_data("AAPL", downloader=RecordingDownloader(pd.DataFrame()))

    def test_raises_for_missing_adjusted_close(self) -> None:
        frame = sample_provider_frame().drop(columns="Adj Close")

        with self.assertRaisesRegex(MarketDataSchemaError, "adjusted_close"):
            load_stock_data("AAPL", downloader=RecordingDownloader(frame))

    def test_wraps_provider_failure_with_ticker_context(self) -> None:
        def failing_downloader(ticker: str, **kwargs: Any) -> pd.DataFrame:
            raise ConnectionError("provider unavailable")

        with self.assertRaisesRegex(MarketDataDownloadError, "AAPL"):
            load_stock_data("AAPL", downloader=failing_downloader)

    def test_live_provider_retries_transient_failures_with_bounded_backoff(self) -> None:
        with (
            TemporaryDirectory() as cache_directory,
            patch.dict(
                os.environ,
                {"QUANTAI_MARKET_DATA_CACHE_DIR": cache_directory},
            ),
            patch(
                "backend.app.quant.data.data_loader._download_with_yfinance",
                side_effect=[
                    ConnectionError("rate limited"),
                    pd.DataFrame(),
                    sample_provider_frame(),
                ],
            ) as downloader,
            patch("backend.app.quant.data.data_loader.time.sleep") as sleep,
        ):
            actual = load_stock_data("MSFT")

        self.assertEqual(downloader.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(0.75), call(2.0)])
        self.assertEqual(actual.attrs["provider_attempts"], 3)
        self.assertFalse(actual.attrs["served_from_cache"])

    def test_provider_failure_uses_exact_persistent_cache(self) -> None:
        def failing_downloader(ticker: str, **kwargs: Any) -> pd.DataFrame:
            raise ConnectionError("provider unavailable")

        with (
            TemporaryDirectory() as cache_directory,
            patch.dict(
                os.environ,
                {"QUANTAI_MARKET_DATA_CACHE_DIR": cache_directory},
            ),
        ):
            live = load_stock_data(
                "AAPL",
                downloader=RecordingDownloader(sample_provider_frame()),
                use_cache=True,
            )
            cached = load_stock_data(
                "AAPL",
                downloader=failing_downloader,
                use_cache=True,
            )

        assert_frame_equal(cached, live)
        self.assertTrue(cached.attrs["served_from_cache"])
        self.assertEqual(cached.attrs["source"], "market-cache")
        self.assertIsInstance(cached.attrs["cached_at_utc"], str)
        self.assertIn("Unable to download market data", cached.attrs["cache_fallback_reason"])

    def test_cache_reuses_an_earlier_starting_compatible_request(self) -> None:
        def failing_downloader(ticker: str, **kwargs: Any) -> pd.DataFrame:
            raise ConnectionError("provider unavailable")

        with (
            TemporaryDirectory() as cache_directory,
            patch.dict(
                os.environ,
                {"QUANTAI_MARKET_DATA_CACHE_DIR": cache_directory},
            ),
        ):
            load_stock_data(
                "AAPL",
                start="2020-01-01",
                downloader=RecordingDownloader(sample_provider_frame()),
                use_cache=True,
            )
            cached = load_stock_data(
                "AAPL",
                start="2024-01-04",
                downloader=failing_downloader,
                use_cache=True,
            )

        self.assertEqual(cached.index.tolist(), [pd.Timestamp("2024-01-04")])
        self.assertTrue(cached.attrs["served_from_cache"])

    def test_cache_does_not_fill_an_earlier_start_from_later_history(self) -> None:
        def failing_downloader(ticker: str, **kwargs: Any) -> pd.DataFrame:
            raise ConnectionError("provider unavailable")

        with (
            TemporaryDirectory() as cache_directory,
            patch.dict(
                os.environ,
                {"QUANTAI_MARKET_DATA_CACHE_DIR": cache_directory},
            ),
        ):
            load_stock_data(
                "AAPL",
                start="2020-01-01",
                downloader=RecordingDownloader(sample_provider_frame()),
                use_cache=True,
            )
            with self.assertRaises(MarketDataDownloadError):
                load_stock_data(
                    "AAPL",
                    start="2019-01-01",
                    downloader=failing_downloader,
                    use_cache=True,
                )


if __name__ == "__main__":
    unittest.main()
