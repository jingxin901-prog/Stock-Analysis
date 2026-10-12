"""Historical daily market-data loading and normalization.

The public loader deliberately returns a narrow, stable DataFrame contract so
the rest of QuantAI does not depend on yfinance-specific column conventions.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Final, TypeAlias

import pandas as pd

from .market_data_cache import read_market_data_cache, write_market_data_cache
from .yfinance_support import configure_yfinance_cache

DateLike: TypeAlias = str | date | datetime | pd.Timestamp
DownloadFunction: TypeAlias = Callable[..., pd.DataFrame]

DEFAULT_START_DATE: Final = "2015-01-01"
STANDARD_COLUMNS: Final = (
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)
_NUMERIC_COLUMNS: Final = (
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
)
_PRICE_COLUMNS: Final = ("open", "high", "low", "close", "adjusted_close")
_TICKER_PATTERN: Final = re.compile(r"^[A-Z0-9^][A-Z0-9.=_^-]{0,19}$")
_COLUMN_ALIASES: Final = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adj_close": "adjusted_close",
    "adjclose": "adjusted_close",
    "adjusted_close": "adjusted_close",
    "volume": "volume",
}


class MarketDataError(RuntimeError):
    """Base exception for market-data loading failures."""


class MarketDataDependencyError(MarketDataError):
    """Raised when the configured data-provider dependency is unavailable."""


class MarketDataDownloadError(MarketDataError):
    """Raised when the upstream provider cannot complete a download."""


class EmptyMarketDataError(MarketDataError):
    """Raised when no usable observations are returned for a request."""


class MarketDataSchemaError(MarketDataError):
    """Raised when provider data cannot satisfy the standardized contract."""


def load_stock_data(
    ticker: str,
    start: DateLike = DEFAULT_START_DATE,
    end: DateLike | None = None,
    *,
    timeout: float = 30.0,
    downloader: DownloadFunction | None = None,
    use_cache: bool | None = None,
) -> pd.DataFrame:
    """Load daily OHLCV history and return a standardized DataFrame.

    Parameters
    ----------
    ticker:
        A Yahoo Finance symbol such as ``AAPL``, ``BRK-B`` or ``0700.HK``.
    start:
        Inclusive start date. The project default is 2015-01-01.
    end:
        Exclusive end date, matching yfinance semantics. ``None`` requests data
        through the latest observation available from the provider.
    timeout:
        Provider request timeout in seconds.
    downloader:
        Optional compatible callable for deterministic tests or another data
        provider adapter.

    Returns
    -------
    pandas.DataFrame
        Ascending, duplicate-free ``DatetimeIndex`` named ``date`` with columns
        ``ticker``, ``open``, ``high``, ``low``, ``close``,
        ``adjusted_close`` and ``volume``.

    Notes
    -----
    Raw OHLC fields are intentionally not auto-adjusted. ``adjusted_close`` is
    preserved separately for total-return research in later modules.
    """

    symbol = normalize_ticker(ticker)
    start_date = _normalize_date(start, parameter_name="start")
    end_date = _normalize_date(end, parameter_name="end") if end is not None else None
    _validate_date_range(start_date, end_date)
    _validate_timeout(timeout)
    if use_cache is not None and not isinstance(use_cache, bool):
        raise TypeError("use_cache must be a boolean or None.")

    download = downloader or _download_with_yfinance
    cache_enabled = downloader is None if use_cache is None else use_cache
    cache_start = start_date.date().isoformat()
    cache_end = end_date.date().isoformat() if end_date is not None else None

    try:
        raw_data = download(
            symbol,
            start=start_date.date().isoformat(),
            end=end_date.date().isoformat() if end_date is not None else None,
            interval="1d",
            auto_adjust=False,
            actions=False,
            prepost=False,
            repair=False,
            keepna=False,
            rounding=False,
            progress=False,
            threads=False,
            ignore_tz=True,
            group_by="column",
            multi_level_index=False,
            timeout=float(timeout),
        )
        data = _standardize_market_data(
            raw_data,
            ticker=symbol,
            requested_start=start_date,
            requested_end=end_date,
        )
    except MarketDataError as exc:
        provider_error: MarketDataError = exc
    except Exception as exc:
        provider_error = MarketDataDownloadError(f"Unable to download market data for {symbol}.")
        provider_error.__cause__ = exc
    else:
        data.attrs["source"] = "yfinance"
        data.attrs["served_from_cache"] = False
        data.attrs["cached_at_utc"] = None
        if cache_enabled:
            write_market_data_cache(
                data,
                ticker=symbol,
                start=cache_start,
                end=cache_end,
            )
        return data

    if cache_enabled:
        cached = read_market_data_cache(ticker=symbol, start=cache_start, end=cache_end)
        if cached is not None:
            data = cached.data
            data.attrs.update(
                {
                    "source": "market-cache",
                    "served_from_cache": True,
                    "cached_at_utc": cached.cached_at_utc,
                    "cache_fallback_reason": str(provider_error),
                    "rows_received": len(data),
                    "rows_returned": len(data),
                }
            )
            return data
    raise provider_error


def _download_with_yfinance(ticker: str, **kwargs: Any) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MarketDataDependencyError(
            "yfinance is not installed. Install the project with "
            "`python -m pip install -e .` before loading live data."
        ) from exc

    configure_yfinance_cache(yf)
    return yf.download(ticker, **kwargs)


def normalize_ticker(ticker: str) -> str:
    """Normalize and validate a Yahoo Finance symbol."""

    if not isinstance(ticker, str):
        raise TypeError("ticker must be a string.")

    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("ticker must not be empty.")
    if not _TICKER_PATTERN.fullmatch(symbol):
        raise ValueError(
            "ticker contains unsupported characters; expected a Yahoo Finance "
            "symbol such as AAPL, BRK-B, 0700.HK or BTC-USD."
        )
    return symbol


def _normalize_date(value: DateLike, *, parameter_name: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{parameter_name} must be a valid date.") from exc

    if pd.isna(timestamp):
        raise ValueError(f"{parameter_name} must be a valid date.")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _validate_date_range(start: pd.Timestamp, end: pd.Timestamp | None) -> None:
    if end is not None and start >= end:
        raise ValueError("start must be earlier than the exclusive end date.")


def _validate_timeout(timeout: float) -> None:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number of seconds.")


def _standardize_market_data(
    raw_data: pd.DataFrame,
    *,
    ticker: str,
    requested_start: pd.Timestamp,
    requested_end: pd.Timestamp | None,
) -> pd.DataFrame:
    if not isinstance(raw_data, pd.DataFrame):
        raise MarketDataSchemaError("The data provider did not return a pandas DataFrame.")
    if raw_data.empty:
        raise EmptyMarketDataError(f"No market data returned for {ticker}.")

    data = raw_data.copy()
    data.columns = [_canonical_column_name(column) for column in data.columns]

    duplicated_columns = data.columns[data.columns.duplicated()].unique().tolist()
    if duplicated_columns:
        raise MarketDataSchemaError(
            "Ambiguous provider response contains duplicate standardized columns: "
            f"{duplicated_columns}."
        )

    missing_columns = [column for column in _NUMERIC_COLUMNS if column not in data.columns]
    if missing_columns:
        raise MarketDataSchemaError(
            f"Provider response for {ticker} is missing columns: {missing_columns}."
        )

    try:
        date_index = pd.DatetimeIndex(pd.to_datetime(data.index, errors="raise"))
    except (TypeError, ValueError) as exc:
        raise MarketDataSchemaError("Provider index cannot be converted to trading dates.") from exc

    if date_index.tz is not None:
        date_index = date_index.tz_localize(None)
    data.index = date_index.normalize()
    data.index.name = "date"

    data = data.loc[:, list(_NUMERIC_COLUMNS)]
    for column in _NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    rows_received = len(data)
    data = data.dropna(subset=list(_NUMERIC_COLUMNS))
    data = data.loc[~data.index.duplicated(keep="last")].sort_index()

    if data.empty:
        raise EmptyMarketDataError(f"No complete daily observations available for {ticker}.")
    if (data["volume"] < 0).any():
        raise MarketDataSchemaError(f"Provider response for {ticker} contains negative volume.")
    if (data["high"] < data["low"]).any():
        raise MarketDataSchemaError(
            f"Provider response for {ticker} contains observations where high is below low."
        )

    data.loc[:, list(_PRICE_COLUMNS)] = data.loc[:, list(_PRICE_COLUMNS)].astype("float64")
    data["volume"] = data["volume"].astype("int64")
    data.insert(0, "ticker", ticker)
    data = data.loc[:, list(STANDARD_COLUMNS)]

    data.attrs.update(
        {
            "source": "yfinance",
            "ticker": ticker,
            "requested_start": requested_start.date().isoformat(),
            "requested_end": (
                requested_end.date().isoformat() if requested_end is not None else None
            ),
            "end_is_exclusive": True,
            "rows_received": rows_received,
            "rows_returned": len(data),
        }
    )
    return data


def _canonical_column_name(column: object) -> str:
    values = column if isinstance(column, tuple) else (column,)
    for value in values:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
        if normalized in _COLUMN_ALIASES:
            return _COLUMN_ALIASES[normalized]

    return "_".join(
        re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_") for value in values
    )
