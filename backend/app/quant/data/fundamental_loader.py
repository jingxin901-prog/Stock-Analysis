"""Current fundamental snapshots for cross-sectional factor research."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, TypeAlias

from .data_loader import normalize_ticker
from .fundamental_cache import read_fundamental_cache, write_fundamental_cache
from .yfinance_support import configure_yfinance_cache

InfoProvider: TypeAlias = Callable[[str], Mapping[str, Any]]


class FundamentalDataError(RuntimeError):
    """Base exception for fundamental-data failures."""


class FundamentalDataDependencyError(FundamentalDataError):
    """Raised when the provider package is unavailable."""


class FundamentalDataDownloadError(FundamentalDataError):
    """Raised when the upstream provider cannot return a snapshot."""


class EmptyFundamentalDataError(FundamentalDataError):
    """Raised when the provider returns no usable mapping."""


@dataclass(frozen=True)
class FundamentalSnapshot:
    """Normalized current fundamental fields used by the factor model."""

    ticker: str
    retrieved_at_utc: str
    pe_ratio: float | None
    pb_ratio: float | None
    ev_to_ebitda: float | None
    roe: float | None
    profit_margin: float | None
    debt_ratio: float | None
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    source: str = "yfinance"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_fundamental_data(
    ticker: str,
    *,
    info_provider: InfoProvider | None = None,
    use_cache: bool | None = None,
) -> FundamentalSnapshot:
    """Load a normalized, retrieval-time fundamental snapshot.

    ``debt_ratio`` is the Yahoo Finance ``debtToEquity`` percentage divided by
    100. It is a leverage proxy rather than total debt divided by total assets.
    Missing provider fields remain ``None`` and are handled by the factor model.
    """

    symbol = normalize_ticker(ticker)
    provider = info_provider or _load_yfinance_info
    cache_enabled = use_cache if use_cache is not None else info_provider is None

    try:
        info = provider(symbol)
    except FundamentalDataError as exc:
        provider_error: FundamentalDataError = exc
    except Exception as exc:
        provider_error = FundamentalDataDownloadError(
            f"Unable to download fundamental data for {symbol}."
        )
        provider_error.__cause__ = exc
    else:
        if not isinstance(info, Mapping) or not info:
            provider_error = EmptyFundamentalDataError(
                f"No fundamental data returned for {symbol}."
            )
        else:
            snapshot = _normalize_snapshot(symbol, info)
            if cache_enabled and _has_useful_data(snapshot):
                write_fundamental_cache(symbol, snapshot.to_dict())
            return snapshot

    if cache_enabled:
        cached = read_fundamental_cache(symbol)
        if cached is not None:
            cached["source"] = "fundamental-cache"
            try:
                return FundamentalSnapshot(**cached)
            except TypeError:
                pass
    raise provider_error


def _normalize_snapshot(symbol: str, info: Mapping[str, Any]) -> FundamentalSnapshot:
    """Map provider fields into the stable application contract."""

    debt_to_equity_percent = _optional_number(info.get("debtToEquity"))
    debt_ratio = debt_to_equity_percent / 100.0 if debt_to_equity_percent is not None else None

    return FundamentalSnapshot(
        ticker=symbol,
        retrieved_at_utc=datetime.now(UTC).isoformat(),
        pe_ratio=_optional_number(info.get("trailingPE")),
        pb_ratio=_optional_number(info.get("priceToBook")),
        ev_to_ebitda=_optional_number(info.get("enterpriseToEbitda")),
        roe=_optional_number(info.get("returnOnEquity")),
        profit_margin=_optional_number(info.get("profitMargins")),
        debt_ratio=debt_ratio,
        company_name=_optional_text(info.get("longName") or info.get("shortName")),
        sector=_optional_text(info.get("sector")),
        industry=_optional_text(info.get("industry")),
        market_cap=_optional_number(info.get("marketCap")),
    )


def _has_useful_data(snapshot: FundamentalSnapshot) -> bool:
    return any(
        value is not None
        for value in (
            snapshot.company_name,
            snapshot.sector,
            snapshot.market_cap,
            snapshot.pe_ratio,
            snapshot.pb_ratio,
            snapshot.roe,
            snapshot.profit_margin,
        )
    )


def _load_yfinance_info(ticker: str) -> Mapping[str, Any]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise FundamentalDataDependencyError(
            "yfinance is not installed. Install the project before loading fundamentals."
        ) from exc

    configure_yfinance_cache(yf)
    return yf.Ticker(ticker).get_info()


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None
