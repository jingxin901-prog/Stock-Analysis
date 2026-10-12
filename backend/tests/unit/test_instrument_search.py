"""Unit tests for resilient global instrument search."""

from __future__ import annotations

import unittest
from typing import Any

from app.quant.data import search_instruments


class _FakeSearch:
    def __init__(self, quotes: list[dict[str, Any]]) -> None:
        self.quotes = quotes


class InstrumentSearchTests(unittest.TestCase):
    def test_local_chinese_alias_is_searchable(self) -> None:
        results, source, warning = search_instruments(
            "贵州茅台",
            search_factory=lambda *_args, **_kwargs: _FakeSearch([]),
        )

        self.assertEqual(results[0].symbol, "600519.SS")
        self.assertEqual(results[0].currency, "CNY")
        self.assertEqual(source, "local")
        self.assertIsNone(warning)

    def test_provider_quotes_are_normalized_and_deduplicated(self) -> None:
        quotes = [
            {
                "symbol": "AAPL",
                "longname": "Apple Inc.",
                "exchDisp": "NASDAQ",
                "quoteType": "EQUITY",
            },
            {"symbol": "AAPL", "shortname": "Duplicate Apple"},
            {"symbol": "7203.T", "shortname": "Toyota Motor Corporation"},
        ]

        results, source, warning = search_instruments(
            "Apple",
            search_factory=lambda *_args, **_kwargs: _FakeSearch(quotes),
        )

        self.assertEqual([result.symbol for result in results], ["AAPL", "7203.T"])
        self.assertEqual(source, "yfinance+local")
        self.assertIsNone(warning)

    def test_provider_failure_preserves_exact_symbol_fallback(self) -> None:
        def unavailable(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("provider unavailable")

        results, source, warning = search_instruments("BRK-B", search_factory=unavailable)

        self.assertEqual(results[0].symbol, "BRK-B")
        self.assertEqual(source, "local")
        self.assertIsNotNone(warning)

    def test_short_query_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            search_instruments("A", search_factory=lambda: _FakeSearch([]))


if __name__ == "__main__":
    unittest.main()
