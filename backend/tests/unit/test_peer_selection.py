"""Tests for the market-, sector-, and size-aware factor peer selector."""

from __future__ import annotations

import unittest

from app.quant.data import classify_market_cap, select_factor_peers


class PeerSelectionTests(unittest.TestCase):
    def test_china_consumer_company_prioritizes_same_sector(self) -> None:
        selection = select_factor_peers(
            "600519.SS",
            sector="Consumer Defensive",
            market_cap=1_500_000_000_000,
        )

        self.assertEqual(selection.tickers[0], "600519.SS")
        self.assertEqual(set(selection.tickers[1:3]), {"000858.SZ", "000568.SZ"})
        self.assertEqual(selection.universe_market, "china_a")
        self.assertEqual(selection.method, "sector_market_cap")
        self.assertEqual(selection.sector, "consumer_defensive")
        self.assertEqual(selection.market_cap_band, "mega")
        self.assertTrue(selection.market_matched)

    def test_unknown_us_symbol_uses_metadata_to_find_comparable_peers(self) -> None:
        selection = select_factor_peers(
            "SMALLER",
            sector="Technology",
            market_cap=50_000_000_000,
        )

        self.assertEqual(selection.tickers[0], "SMALLER")
        self.assertEqual(selection.tickers[1], "CRM")
        self.assertEqual(selection.method, "sector_market_cap")
        self.assertEqual(selection.market_cap_band, "large")
        self.assertEqual(len(selection.tickers), 6)

    def test_missing_metadata_uses_stable_same_market_fallback(self) -> None:
        selection = select_factor_peers(
            "688001.SS",
            sector=None,
            market_cap=None,
        )

        self.assertEqual(selection.tickers[0], "688001.SS")
        self.assertEqual(selection.method, "market_fallback")
        self.assertTrue(all(ticker.endswith((".SS", ".SZ")) for ticker in selection.tickers))

    def test_unsupported_market_is_explicit_global_fallback(self) -> None:
        selection = select_factor_peers(
            "7203.T",
            sector="Consumer Cyclical",
            market_cap=50_000_000_000_000,
        )

        self.assertEqual(selection.method, "global_fallback")
        self.assertEqual(selection.universe_market, "global")
        self.assertFalse(selection.market_matched)
        self.assertEqual(selection.tickers[0], "7203.T")

    def test_market_cap_bands_use_market_native_thresholds(self) -> None:
        self.assertEqual(classify_market_cap("us", 250_000_000_000), "mega")
        self.assertEqual(classify_market_cap("china_a", 150_000_000_000), "large")
        self.assertEqual(classify_market_cap("hong_kong", 4_000_000_000), "micro")
        self.assertIsNone(classify_market_cap("japan", 1_000_000_000_000))


if __name__ == "__main__":
    unittest.main()
