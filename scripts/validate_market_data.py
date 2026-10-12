"""Run reproducible live-data quality checks for the QuantAI sample universe."""

from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from app.quant.data import DEFAULT_START_DATE, STANDARD_COLUMNS, load_stock_data

DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL")
DEFAULT_REPORT_PATH = Path("artifacts/validation/market_data_validation.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and validate standardized daily market data."
    )
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_TICKERS))
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument(
        "--max-latest-age-days",
        type=int,
        default=14,
        help="Maximum calendar age allowed for the latest daily observation.",
    )
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def validate_frame(
    frame: pd.DataFrame,
    *,
    ticker: str,
    requested_start: pd.Timestamp,
    max_latest_age_days: int,
) -> dict[str, Any]:
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    first_date = frame.index.min()
    last_date = frame.index.max()
    latest_age_days = int((today - last_date).days)

    price_columns = ["open", "high", "low", "close", "adjusted_close"]
    ohlc_consistent = bool(
        (
            (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
            & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
        ).all()
    )

    checks = {
        "non_empty": not frame.empty,
        "columns_match_contract": tuple(frame.columns) == STANDARD_COLUMNS,
        "ticker_is_consistent": bool(frame["ticker"].eq(ticker).all()),
        "index_is_datetime": isinstance(frame.index, pd.DatetimeIndex),
        "index_is_ascending": frame.index.is_monotonic_increasing,
        "index_is_unique": frame.index.is_unique,
        "no_missing_values": not bool(frame.isna().any().any()),
        "price_columns_are_numeric": all(
            pd.api.types.is_numeric_dtype(frame[column]) for column in price_columns
        ),
        "volume_is_integer": pd.api.types.is_integer_dtype(frame["volume"]),
        "volume_is_nonnegative": bool(frame["volume"].ge(0).all()),
        "ohlc_is_consistent": ohlc_consistent,
        "starts_near_requested_date": bool(first_date <= requested_start + pd.Timedelta(days=10)),
        "latest_observation_is_recent": 0 <= latest_age_days <= max_latest_age_days,
    }

    return {
        "ticker": ticker,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "statistics": {
            "row_count": len(frame),
            "first_date": first_date.date().isoformat(),
            "last_date": last_date.date().isoformat(),
            "latest_age_days": latest_age_days,
            "duplicate_dates": int(frame.index.duplicated().sum()),
            "missing_cells": int(frame.isna().sum().sum()),
            "minimum_close": float(frame["close"].min()),
            "maximum_close": float(frame["close"].max()),
            "zero_volume_days": int(frame["volume"].eq(0).sum()),
        },
    }


def validate_ticker(
    ticker: str,
    *,
    start: str,
    max_latest_age_days: int,
) -> dict[str, Any]:
    symbol = ticker.strip().upper()
    requested_start = pd.Timestamp(start).normalize()
    try:
        frame = load_stock_data(symbol, start=requested_start)
        return validate_frame(
            frame,
            ticker=symbol,
            requested_start=requested_start,
            max_latest_age_days=max_latest_age_days,
        )
    except Exception as exc:  # report provider and contract failures uniformly
        return {
            "ticker": symbol,
            "status": "error",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def print_summary(results: list[dict[str, Any]]) -> None:
    print(f"{'Ticker':<8} {'Status':<8} {'Rows':>7} {'First':>12} {'Last':>12} {'Age':>5}")
    print("-" * 58)
    for result in results:
        statistics = result.get("statistics", {})
        print(
            f"{result['ticker']:<8} "
            f"{result['status']:<8} "
            f"{statistics.get('row_count', '-'):>7} "
            f"{statistics.get('first_date', '-'):>12} "
            f"{statistics.get('last_date', '-'):>12} "
            f"{statistics.get('latest_age_days', '-'):>5}"
        )
        if "error" in result:
            print(f"  {result['error']['type']}: {result['error']['message']}")


def main() -> int:
    args = parse_args()
    if args.max_latest_age_days < 0:
        raise SystemExit("--max-latest-age-days must be nonnegative.")
    if args.pause_seconds < 0:
        raise SystemExit("--pause-seconds must be nonnegative.")

    started_at = datetime.now(UTC)
    results: list[dict[str, Any]] = []
    for index, ticker in enumerate(args.tickers):
        results.append(
            validate_ticker(
                ticker,
                start=args.start,
                max_latest_age_days=args.max_latest_age_days,
            )
        )
        if index < len(args.tickers) - 1 and args.pause_seconds:
            time.sleep(args.pause_seconds)

    completed_at = datetime.now(UTC)
    passed = sum(result["status"] == "passed" for result in results)
    report = {
        "schema_version": 1,
        "started_at_utc": started_at.isoformat(),
        "completed_at_utc": completed_at.isoformat(),
        "requested_start": args.start,
        "max_latest_age_days": args.max_latest_age_days,
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "yfinance": yf.__version__,
        },
        "summary": {
            "ticker_count": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "all_passed": passed == len(results),
        },
        "results": results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_summary(results)
    print(f"\nReport: {args.output.resolve()}")
    return 0 if report["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
