"""Search Yahoo Finance instruments with a small resilient local fallback."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final

from .data_loader import normalize_ticker
from .instrument_context import get_instrument_context
from .yfinance_support import configure_yfinance_cache

SearchFactory = Callable[..., Any]


@dataclass(frozen=True)
class InstrumentSearchRecord:
    """Normalized search result consumed by the API and dashboard."""

    symbol: str
    name: str
    exchange: str
    quote_type: str
    market: str
    currency: str


LOCAL_INSTRUMENTS: Final = (
    ("600519.SS", "贵州茅台 / Kweichow Moutai", "Shanghai"),
    ("000858.SZ", "五粮液 / Wuliangye", "Shenzhen"),
    ("300750.SZ", "宁德时代 / CATL", "Shenzhen"),
    ("002594.SZ", "比亚迪 / BYD", "Shenzhen"),
    ("601318.SS", "中国平安 / Ping An Insurance", "Shanghai"),
    ("600036.SS", "招商银行 / China Merchants Bank", "Shanghai"),
    ("0700.HK", "腾讯控股 / Tencent", "Hong Kong"),
    ("9988.HK", "阿里巴巴 / Alibaba", "Hong Kong"),
    ("3690.HK", "美团 / Meituan", "Hong Kong"),
    ("AAPL", "Apple Inc.", "NASDAQ"),
    ("MSFT", "Microsoft Corporation", "NASDAQ"),
    ("NVDA", "NVIDIA Corporation", "NASDAQ"),
    ("TSLA", "Tesla, Inc.", "NASDAQ"),
    ("AMZN", "Amazon.com, Inc.", "NASDAQ"),
    ("GOOGL", "Alphabet Inc.", "NASDAQ"),
)


def search_instruments(
    query: str,
    *,
    limit: int = 8,
    search_factory: SearchFactory | None = None,
) -> tuple[list[InstrumentSearchRecord], str, str | None]:
    """Return normalized instrument matches and provider-status metadata."""

    cleaned_query = _validate_query(query)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20.")

    local_results = _search_local(cleaned_query)
    provider_warning: str | None = None
    provider_results: list[InstrumentSearchRecord] = []
    try:
        factory = search_factory or _yfinance_search_factory()
        search = factory(
            cleaned_query,
            max_results=limit,
            news_count=0,
            lists_count=0,
            include_cb=False,
            include_nav_links=False,
            include_research=False,
            include_cultural_assets=False,
            enable_fuzzy_query=True,
            recommended=0,
            timeout=8,
            raise_errors=True,
        )
        provider_results = _normalize_provider_quotes(search.quotes)
    except Exception:
        provider_warning = (
            "Live symbol search is temporarily unavailable; local matches and exact "
            "Yahoo Finance symbols remain available."
        )

    results = _deduplicate([*local_results, *provider_results])
    exact = _exact_symbol_fallback(cleaned_query)
    if exact is not None and all(item.symbol != exact.symbol for item in results):
        results.append(exact)

    source = "yfinance+local" if provider_results else "local"
    return results[:limit], source, provider_warning


def _yfinance_search_factory() -> SearchFactory:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for live instrument search.") from exc
    configure_yfinance_cache(yf)
    return yf.Search


def _validate_query(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("query must be a string.")
    cleaned = " ".join(query.strip().split())
    if len(cleaned) < 2:
        raise ValueError("query must contain at least two characters.")
    if len(cleaned) > 64:
        raise ValueError("query must contain at most 64 characters.")
    if any(ord(character) < 32 for character in cleaned):
        raise ValueError("query contains unsupported control characters.")
    return cleaned


def _search_local(query: str) -> list[InstrumentSearchRecord]:
    needle = query.casefold()
    records: list[InstrumentSearchRecord] = []
    for symbol, name, exchange in LOCAL_INSTRUMENTS:
        if needle not in f"{symbol} {name} {exchange}".casefold():
            continue
        records.append(_record(symbol, name, exchange, "Equity"))
    return records


def _normalize_provider_quotes(quotes: Iterable[dict[str, Any]]) -> list[InstrumentSearchRecord]:
    records: list[InstrumentSearchRecord] = []
    for quote in quotes:
        raw_symbol = quote.get("symbol")
        if not isinstance(raw_symbol, str):
            continue
        try:
            symbol = normalize_ticker(raw_symbol)
        except (TypeError, ValueError):
            continue
        name = str(quote.get("longname") or quote.get("shortname") or quote.get("name") or symbol)
        exchange = str(
            quote.get("exchDisp")
            or quote.get("fullExchangeName")
            or quote.get("exchange")
            or "Yahoo Finance"
        )
        quote_type = str(quote.get("typeDisp") or quote.get("quoteType") or "Instrument")
        records.append(_record(symbol, name, exchange, quote_type))
    return records


def _exact_symbol_fallback(query: str) -> InstrumentSearchRecord | None:
    if not query.isascii() or query != query.upper():
        return None
    if query.isdecimal() and len(query) == 6:
        return None
    try:
        symbol = normalize_ticker(query)
    except (TypeError, ValueError):
        return None
    return _record(symbol, "Exact Yahoo Finance symbol", "Yahoo Finance", "Instrument")


def _record(symbol: str, name: str, exchange: str, quote_type: str) -> InstrumentSearchRecord:
    context = get_instrument_context(symbol)
    return InstrumentSearchRecord(
        symbol=symbol,
        name=name,
        exchange=exchange,
        quote_type=quote_type,
        market=context.market,
        currency=context.currency,
    )


def _deduplicate(records: Iterable[InstrumentSearchRecord]) -> list[InstrumentSearchRecord]:
    unique: dict[str, InstrumentSearchRecord] = {}
    for record in records:
        unique.setdefault(record.symbol, record)
    return list(unique.values())
