"""Deterministic, market-aware peer selection for factor research.

The target company's sector and market capitalization come from its current
Yahoo Finance snapshot. Peers are selected from a deliberately small,
documented candidate catalog so the dashboard remains fast and reproducible.
The catalog is not intended to represent an investable index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .data_loader import normalize_ticker
from .instrument_context import get_instrument_context


@dataclass(frozen=True)
class PeerCandidate:
    """A stable candidate used to construct a comparable factor cross-section."""

    ticker: str
    market: str
    sector: str
    market_cap_band: str


@dataclass(frozen=True)
class FactorPeerSelection:
    """Selected factor universe and the evidence used to construct it."""

    tickers: tuple[str, ...]
    label: str
    universe_market: str
    market_matched: bool
    method: str
    sector: str | None
    market_cap_band: str | None


_BAND_ORDER: Final = {"micro": 0, "small": 1, "mid": 2, "large": 3, "mega": 4}

# Thresholds are expressed in each market's native quote currency. They are
# broad research buckets, not index-provider classifications.
_MARKET_CAP_THRESHOLDS: Final = {
    "us": (
        (200_000_000_000, "mega"),
        (10_000_000_000, "large"),
        (2_000_000_000, "mid"),
        (300_000_000, "small"),
    ),
    "china_a": (
        (1_000_000_000_000, "mega"),
        (100_000_000_000, "large"),
        (20_000_000_000, "mid"),
        (5_000_000_000, "small"),
    ),
    "hong_kong": (
        (1_000_000_000_000, "mega"),
        (100_000_000_000, "large"),
        (20_000_000_000, "mid"),
        (5_000_000_000, "small"),
    ),
}

_LABELS: Final = {
    "us": "US sector-aware peer universe",
    "china_a": "China A-share sector-aware peer universe",
    "hong_kong": "Hong Kong sector-aware peer universe",
}

PEER_CATALOG: Final[tuple[PeerCandidate, ...]] = (
    # United States
    PeerCandidate("AAPL", "us", "technology", "mega"),
    PeerCandidate("MSFT", "us", "technology", "mega"),
    PeerCandidate("NVDA", "us", "technology", "mega"),
    PeerCandidate("AVGO", "us", "technology", "mega"),
    PeerCandidate("ORCL", "us", "technology", "mega"),
    PeerCandidate("CRM", "us", "technology", "large"),
    PeerCandidate("TSLA", "us", "consumer_cyclical", "mega"),
    PeerCandidate("AMZN", "us", "consumer_cyclical", "mega"),
    PeerCandidate("HD", "us", "consumer_cyclical", "mega"),
    PeerCandidate("GOOGL", "us", "communication_services", "mega"),
    PeerCandidate("META", "us", "communication_services", "mega"),
    PeerCandidate("NFLX", "us", "communication_services", "large"),
    PeerCandidate("JPM", "us", "financials", "mega"),
    PeerCandidate("BAC", "us", "financials", "large"),
    PeerCandidate("JNJ", "us", "healthcare", "mega"),
    PeerCandidate("LLY", "us", "healthcare", "mega"),
    PeerCandidate("XOM", "us", "energy", "mega"),
    PeerCandidate("CVX", "us", "energy", "mega"),
    # Mainland China
    PeerCandidate("600519.SS", "china_a", "consumer_defensive", "mega"),
    PeerCandidate("000858.SZ", "china_a", "consumer_defensive", "large"),
    PeerCandidate("000568.SZ", "china_a", "consumer_defensive", "large"),
    PeerCandidate("601318.SS", "china_a", "financials", "mega"),
    PeerCandidate("600036.SS", "china_a", "financials", "mega"),
    PeerCandidate("601398.SS", "china_a", "financials", "mega"),
    PeerCandidate("300750.SZ", "china_a", "industrials", "mega"),
    PeerCandidate("601012.SS", "china_a", "industrials", "large"),
    PeerCandidate("002594.SZ", "china_a", "consumer_cyclical", "mega"),
    PeerCandidate("600276.SS", "china_a", "healthcare", "large"),
    PeerCandidate("300760.SZ", "china_a", "healthcare", "large"),
    PeerCandidate("600900.SS", "china_a", "utilities", "mega"),
    # Hong Kong
    PeerCandidate("0700.HK", "hong_kong", "communication_services", "mega"),
    PeerCandidate("0941.HK", "hong_kong", "communication_services", "mega"),
    PeerCandidate("9988.HK", "hong_kong", "consumer_cyclical", "mega"),
    PeerCandidate("3690.HK", "hong_kong", "consumer_cyclical", "mega"),
    PeerCandidate("9618.HK", "hong_kong", "consumer_cyclical", "large"),
    PeerCandidate("1299.HK", "hong_kong", "financials", "mega"),
    PeerCandidate("2318.HK", "hong_kong", "financials", "mega"),
    PeerCandidate("0005.HK", "hong_kong", "financials", "large"),
    PeerCandidate("0939.HK", "hong_kong", "financials", "mega"),
    PeerCandidate("0388.HK", "hong_kong", "financials", "large"),
    PeerCandidate("0883.HK", "hong_kong", "energy", "mega"),
    PeerCandidate("0016.HK", "hong_kong", "real_estate", "large"),
)


def normalize_sector(value: str | None) -> str | None:
    """Normalize Yahoo sector labels to stable cross-market categories."""

    if not value:
        return None
    normalized = "_".join(value.strip().casefold().replace("&", "and").split())
    aliases = {
        "financial_services": "financials",
        "basic_materials": "materials",
        "communication_service": "communication_services",
        "consumer_discretionary": "consumer_cyclical",
        "consumer_staples": "consumer_defensive",
    }
    return aliases.get(normalized, normalized)


def classify_market_cap(market: str, market_cap: float | None) -> str | None:
    """Classify capitalization using transparent native-currency thresholds."""

    if market_cap is None or market_cap <= 0:
        return None
    thresholds = _MARKET_CAP_THRESHOLDS.get(market)
    if thresholds is None:
        return None
    for threshold, band in thresholds:
        if market_cap >= threshold:
            return band
    return "micro"


def select_factor_peers(
    ticker: str,
    *,
    sector: str | None,
    market_cap: float | None,
    max_size: int = 6,
) -> FactorPeerSelection:
    """Select the target and up to five comparable, same-market peers.

    Same-sector candidates are ranked first, followed by the closest broad
    capitalization bucket. Missing metadata gracefully falls back to a stable
    market universe. Unsupported markets retain the existing disclosed global
    fallback rather than pretending the sample is locally comparable.
    """

    if max_size < 2:
        raise ValueError("max_size must be at least 2.")

    symbol = normalize_ticker(ticker)
    context = get_instrument_context(symbol)
    market_candidates = [
        candidate for candidate in PEER_CATALOG if candidate.market == context.market
    ]

    if not market_candidates:
        fallback = _dedupe((symbol, *context.factor_universe))[:max_size]
        return FactorPeerSelection(
            tickers=fallback,
            label=context.factor_universe_label,
            universe_market="global",
            market_matched=False,
            method="global_fallback",
            sector=normalize_sector(sector),
            market_cap_band=None,
        )

    catalog_target = next(
        (candidate for candidate in market_candidates if candidate.ticker == symbol),
        None,
    )
    target_sector = normalize_sector(sector) or (
        catalog_target.sector if catalog_target is not None else None
    )
    target_band = classify_market_cap(context.market, market_cap) or (
        catalog_target.market_cap_band if catalog_target is not None else None
    )

    peers = [candidate for candidate in market_candidates if candidate.ticker != symbol]
    peers.sort(key=lambda candidate: _peer_sort_key(candidate, target_sector, target_band))
    selected = (symbol, *(candidate.ticker for candidate in peers[: max_size - 1]))

    same_sector_available = bool(
        target_sector and any(candidate.sector == target_sector for candidate in peers)
    )
    if same_sector_available and target_band:
        method = "sector_market_cap"
    elif same_sector_available:
        method = "sector"
    elif target_band:
        method = "market_cap"
    else:
        method = "market_fallback"

    return FactorPeerSelection(
        tickers=selected,
        label=_LABELS[context.market],
        universe_market=context.market,
        market_matched=True,
        method=method,
        sector=target_sector,
        market_cap_band=target_band,
    )


def _peer_sort_key(
    candidate: PeerCandidate,
    target_sector: str | None,
    target_band: str | None,
) -> tuple[int, int, str]:
    sector_penalty = int(target_sector is not None and candidate.sector != target_sector)
    band_distance = (
        abs(_BAND_ORDER[candidate.market_cap_band] - _BAND_ORDER[target_band])
        if target_band is not None
        else 0
    )
    return sector_penalty, band_distance, candidate.ticker


def _dedupe(tickers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tickers))
