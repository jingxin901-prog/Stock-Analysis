"""Market-aware metadata for Yahoo Finance symbols.

The price loader intentionally accepts Yahoo Finance symbols from many markets.
This module adds a small, deterministic layer that the research UI can use for
peer selection, benchmark defaults, and currency disclosures without making an
additional provider request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .data_loader import normalize_ticker


@dataclass(frozen=True)
class InstrumentContext:
    """Deterministic market metadata inferred from a Yahoo Finance symbol."""

    market: str
    currency: str
    suggested_benchmark: str
    factor_universe: tuple[str, ...]
    factor_universe_label: str
    market_matched_factors: bool


US_FACTOR_UNIVERSE: Final = (
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "GOOGL",
)
CHINA_A_FACTOR_UNIVERSE: Final = (
    "600519.SS",
    "601318.SS",
    "600036.SS",
    "000858.SZ",
    "300750.SZ",
    "002594.SZ",
)
HONG_KONG_FACTOR_UNIVERSE: Final = (
    "0700.HK",
    "9988.HK",
    "3690.HK",
    "1299.HK",
    "2318.HK",
    "0005.HK",
)

_INTERNATIONAL_MARKETS: Final = {
    ".L": ("united_kingdom", "GBP", "^FTSE"),
    ".TO": ("canada", "CAD", "^GSPTSE"),
    ".T": ("japan", "JPY", "^N225"),
    ".AX": ("australia", "AUD", "^AXJO"),
    ".DE": ("germany", "EUR", "^GDAXI"),
    ".PA": ("france", "EUR", "^FCHI"),
}


def get_instrument_context(ticker: str) -> InstrumentContext:
    """Infer market, quote currency, benchmark, and a compact factor peer set."""

    symbol = normalize_ticker(ticker)
    if symbol.endswith((".SS", ".SZ")):
        return InstrumentContext(
            market="china_a",
            currency="CNY",
            suggested_benchmark="000001.SS",
            factor_universe=CHINA_A_FACTOR_UNIVERSE,
            factor_universe_label="China A-share reference universe",
            market_matched_factors=True,
        )
    if symbol.endswith(".HK"):
        return InstrumentContext(
            market="hong_kong",
            currency="HKD",
            suggested_benchmark="^HSI",
            factor_universe=HONG_KONG_FACTOR_UNIVERSE,
            factor_universe_label="Hong Kong reference universe",
            market_matched_factors=True,
        )
    for suffix, (market, currency, benchmark) in _INTERNATIONAL_MARKETS.items():
        if symbol.endswith(suffix):
            return InstrumentContext(
                market=market,
                currency=currency,
                suggested_benchmark=benchmark,
                factor_universe=US_FACTOR_UNIVERSE,
                factor_universe_label="Global fallback reference universe",
                market_matched_factors=False,
            )
    return InstrumentContext(
        market="us",
        currency="USD",
        suggested_benchmark="SPY",
        factor_universe=US_FACTOR_UNIVERSE,
        factor_universe_label="US large-cap technology reference universe",
        market_matched_factors=True,
    )


def infer_portfolio_benchmark(tickers: list[str]) -> str:
    """Return a market-aware default benchmark for a portfolio universe."""

    contexts = [get_instrument_context(ticker) for ticker in tickers]
    markets = {context.market for context in contexts}
    if len(markets) == 1:
        return contexts[0].suggested_benchmark
    return "ACWI"


def portfolio_quote_currencies(tickers: list[str]) -> tuple[str, ...]:
    """Return the sorted native quote currencies represented by a universe."""

    return tuple(sorted({get_instrument_context(ticker).currency for ticker in tickers}))
