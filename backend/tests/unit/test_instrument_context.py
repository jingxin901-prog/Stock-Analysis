"""Tests for market-aware symbol metadata and benchmark inference."""

from __future__ import annotations

import unittest

from app.quant.data import (
    get_instrument_context,
    infer_portfolio_benchmark,
    portfolio_quote_currencies,
)


class InstrumentContextTests(unittest.TestCase):
    def test_china_a_share_uses_local_peers_and_csi_300(self) -> None:
        context = get_instrument_context("600519.ss")

        self.assertEqual(context.market, "china_a")
        self.assertEqual(context.currency, "CNY")
        self.assertEqual(context.suggested_benchmark, "000001.SS")
        self.assertTrue(context.market_matched_factors)
        self.assertTrue(all(ticker.endswith((".SS", ".SZ")) for ticker in context.factor_universe))

    def test_hong_kong_share_uses_hang_seng_context(self) -> None:
        context = get_instrument_context("0700.hk")

        self.assertEqual(context.market, "hong_kong")
        self.assertEqual(context.currency, "HKD")
        self.assertEqual(context.suggested_benchmark, "^HSI")

    def test_international_market_discloses_fallback_factor_universe(self) -> None:
        context = get_instrument_context("7203.T")

        self.assertEqual(context.market, "japan")
        self.assertEqual(context.currency, "JPY")
        self.assertFalse(context.market_matched_factors)

    def test_portfolio_benchmark_is_market_aware(self) -> None:
        self.assertEqual(infer_portfolio_benchmark(["600519.SS", "000858.SZ"]), "000001.SS")
        self.assertEqual(infer_portfolio_benchmark(["0700.HK", "9988.HK"]), "^HSI")
        self.assertEqual(infer_portfolio_benchmark(["AAPL", "0700.HK"]), "ACWI")

    def test_quote_currencies_identify_cross_market_universe(self) -> None:
        self.assertEqual(
            portfolio_quote_currencies(["AAPL", "600519.SS", "0700.HK"]),
            ("CNY", "HKD", "USD"),
        )


if __name__ == "__main__":
    unittest.main()
