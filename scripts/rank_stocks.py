"""Build and rank the current QuantAI factor universe."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from app.quant.data import DEFAULT_START_DATE, load_fundamental_data, load_stock_data
from app.quant.factors import build_factor_record, score_factor_universe

DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL")
DEFAULT_OUTPUT = Path("artifacts/analysis/factor_ranking.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank a stock universe using QuantAI factors.")
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_TICKERS))
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    safe_frame = frame.astype(object).where(pd.notna(frame), None)
    return safe_frame.to_dict(orient="records")


def main() -> int:
    args = parse_args()
    factor_records: list[dict[str, str | float | None]] = []
    retrieval_times: dict[str, str] = {}

    for ticker in args.tickers:
        prices = load_stock_data(ticker, start=args.start)
        fundamentals = load_fundamental_data(ticker)
        factor_records.append(build_factor_record(fundamentals, prices))
        retrieval_times[fundamentals.ticker] = fundamentals.retrieved_at_utc

    ranking = score_factor_universe(pd.DataFrame(factor_records))
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "requested_price_start": args.start,
        "fundamental_retrieval_times_utc": retrieval_times,
        "methodology": {
            "winsor_limits": [0.05, 0.95],
            "missing_component_score": 50.0,
            "factor_weights": {"value": 1 / 3, "momentum": 1 / 3, "quality": 1 / 3},
            "debt_ratio_definition": "Yahoo debtToEquity divided by 100",
        },
        "ranking": json_records(ranking),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        ranking[
            [
                "rank",
                "ticker",
                "value_score",
                "momentum_score",
                "quality_score",
                "quant_score",
                "data_coverage",
            ]
        ].to_string(index=False)
    )
    print(f"\nReport: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
