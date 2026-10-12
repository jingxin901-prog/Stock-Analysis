"""Small, transparent on-disk fallback cache for standardized market data."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

_CACHE_LOCK = threading.Lock()
_CACHE_VERSION = 1


@dataclass(frozen=True)
class MarketDataCacheEntry:
    data: pd.DataFrame
    cached_at_utc: str


def write_market_data_cache(
    data: pd.DataFrame,
    *,
    ticker: str,
    start: str,
    end: str | None,
) -> str | None:
    """Atomically persist one exact standardized market-data request."""

    cache_directory = _cache_directory()
    key = _cache_key(ticker=ticker, start=start, end=end)
    data_path = cache_directory / f"{key}.csv"
    metadata_path = cache_directory / f"{key}.json"
    cached_at_utc = datetime.now(UTC).isoformat()
    metadata = {
        "version": _CACHE_VERSION,
        "ticker": ticker,
        "start": start,
        "end": end,
        "cached_at_utc": cached_at_utc,
        "observations": len(data),
        "first_observation": data.index[0].date().isoformat(),
        "last_observation": data.index[-1].date().isoformat(),
    }
    temporary_data: Path | None = None
    temporary_metadata: Path | None = None
    try:
        with _CACHE_LOCK:
            cache_directory.mkdir(parents=True, exist_ok=True)
            temporary_data = _temporary_path(cache_directory, ".csv")
            temporary_metadata = _temporary_path(cache_directory, ".json")
            data.to_csv(temporary_data, index=True, index_label="date")
            temporary_metadata.write_text(
                json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary_data.replace(data_path)
            temporary_metadata.replace(metadata_path)
    except (OSError, TypeError, ValueError):
        for path in (temporary_data, temporary_metadata):
            if path is not None:
                with suppress(OSError):
                    path.unlink()
        return None
    return cached_at_utc


def read_market_data_cache(
    *,
    ticker: str,
    start: str,
    end: str | None,
) -> MarketDataCacheEntry | None:
    """Read the newest cache entry whose requested range covers this request.

    Reusing an earlier-starting open-ended history keeps daily dashboard routes
    available when their rolling start date changes while the provider is down.
    A cache created for a later start date is never used for an earlier request.
    """

    cache_directory = _cache_directory()
    exact_key = _cache_key(ticker=ticker, start=start, end=end)
    candidates: list[tuple[bool, str, Path, dict[str, object]]] = []
    try:
        with _CACHE_LOCK:
            for metadata_path in cache_directory.glob("*.json"):
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (OSError, TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(metadata, dict):
                    continue
                cached_start = metadata.get("start")
                cached_at_utc = metadata.get("cached_at_utc")
                if (
                    metadata.get("version") != _CACHE_VERSION
                    or metadata.get("ticker") != ticker
                    or metadata.get("end") != end
                    or not isinstance(cached_start, str)
                    or cached_start > start
                    or not isinstance(cached_at_utc, str)
                    or not cached_at_utc
                ):
                    continue
                candidates.append(
                    (
                        metadata_path.stem == exact_key,
                        cached_at_utc,
                        metadata_path.with_suffix(".csv"),
                        metadata,
                    )
                )

            candidates.sort(key=lambda candidate: (candidate[1], candidate[0]), reverse=True)
            for _, cached_at_utc, data_path, _ in candidates:
                entry = _read_cache_candidate(
                    data_path,
                    ticker=ticker,
                    start=start,
                    end=end,
                    cached_at_utc=cached_at_utc,
                )
                if entry is not None:
                    return entry
    except OSError:
        return None
    return None


def _read_cache_candidate(
    data_path: Path,
    *,
    ticker: str,
    start: str,
    end: str | None,
    cached_at_utc: str,
) -> MarketDataCacheEntry | None:
    try:
        data = pd.read_csv(data_path, parse_dates=["date"], index_col="date")
    except (OSError, ValueError, TypeError):
        return None

    required_columns = {
        "ticker",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
    }
    if data.empty or not required_columns.issubset(data.columns):
        return None
    if not isinstance(data.index, pd.DatetimeIndex):
        return None
    data.index.name = "date"
    data = data.sort_index()
    if data.index.has_duplicates or not data["ticker"].eq(ticker).all():
        return None
    numeric_columns = ["open", "high", "low", "close", "adjusted_close", "volume"]
    numeric = data[numeric_columns].apply(pd.to_numeric, errors="coerce")
    price_columns = ["open", "high", "low", "close", "adjusted_close"]
    if numeric.isna().any().any() or (numeric[price_columns] <= 0).any().any():
        return None
    data[numeric.columns] = numeric

    requested_start = pd.Timestamp(start)
    data = data.loc[data.index >= requested_start]
    if end is not None:
        data = data.loc[data.index < pd.Timestamp(end)]
    if data.empty:
        return None
    return MarketDataCacheEntry(data=data, cached_at_utc=cached_at_utc)


def _cache_directory() -> Path:
    configured_path = os.getenv("QUANTAI_MARKET_DATA_CACHE_DIR")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(tempfile.gettempdir()) / "quantai-market-data-cache"


def _cache_key(*, ticker: str, start: str, end: str | None) -> str:
    request = json.dumps(
        {"ticker": ticker, "start": start, "end": end},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(request.encode("utf-8")).hexdigest()


def _temporary_path(directory: Path, suffix: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix="quantai-", suffix=suffix, dir=directory)
    os.close(descriptor)
    return Path(raw_path)
