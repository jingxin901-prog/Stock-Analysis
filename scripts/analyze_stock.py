"""Download a stock and print the standard QuantAI financial metric summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.quant.data import DEFAULT_START_DATE, load_stock_data
from app.quant.metrics import calculate_financial_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate return and risk metrics for one stock.")
    parser.add_argument("ticker")
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--end", default=None, help="Exclusive end date.")
    parser.add_argument("--risk-free-rate", type=float, default=0.0)
    parser.add_argument("--var-confidence", type=float, default=0.95)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def format_optional_ratio(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.4f}"


def main() -> int:
    args = parse_args()
    market_data = load_stock_data(args.ticker, start=args.start, end=args.end)
    metrics = calculate_financial_metrics(
        market_data,
        risk_free_rate=args.risk_free_rate,
        var_confidence_level=args.var_confidence,
    )
    result = metrics.to_dict()

    print(f"Stock: {metrics.ticker or args.ticker.upper()}")
    print(f"Observation Window: {metrics.start_date} to {metrics.end_date}")
    print(f"Annualized Return: {metrics.annualized_return:.2%}")
    print(f"Annualized Volatility: {metrics.annualized_volatility:.2%}")
    print(f"Sharpe Ratio: {format_optional_ratio(metrics.sharpe_ratio)}")
    print(f"Maximum Drawdown: {metrics.maximum_drawdown:.2%}")
    print(
        f"Historical VaR ({metrics.var_confidence_level:.0%}, daily): "
        f"{metrics.value_at_risk:.2%} loss"
    )

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
