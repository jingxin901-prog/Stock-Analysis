"""Run constrained portfolio optimization, frontier, and Monte Carlo analysis."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from app.quant.data import DEFAULT_START_DATE, load_stock_data
from app.quant.portfolio import (
    calculate_efficient_frontier,
    estimate_market_inputs,
    optimize_max_sharpe,
    optimize_minimum_volatility,
    prepare_price_matrix,
)
from app.quant.portfolio.visualization import write_portfolio_analysis_html
from app.quant.simulation import simulate_portfolio_paths

DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA", "TSLA")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize and simulate a stock portfolio.")
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_TICKERS))
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--risk-free-rate", type=float, default=0.0)
    parser.add_argument("--cash-weight", type=float, default=0.15)
    parser.add_argument("--min-weight", type=float, default=0.0)
    parser.add_argument("--max-weight", type=float, default=0.60)
    parser.add_argument("--frontier-points", type=int, default=30)
    parser.add_argument("--initial-value", type=float, default=100_000.0)
    parser.add_argument("--simulation-paths", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/analysis/portfolio_optimization.json"),
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=Path("outputs/portfolio_analysis.html"),
    )
    return parser.parse_args()


def json_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    safe = frame.astype(object).where(pd.notna(frame), None)
    return safe.to_dict(orient="records")


def print_result(label: str, result: Any) -> None:
    print(label)
    for ticker, weight in result.weights.items():
        print(f"  {ticker}: {weight:.2%}")
    print(f"  Cash: {result.cash_weight:.2%}")
    print(f"  Expected Return: {result.expected_return:.2%}")
    print(f"  Volatility: {result.volatility:.2%}")
    sharpe = "undefined" if result.sharpe_ratio is None else f"{result.sharpe_ratio:.4f}"
    print(f"  Sharpe Ratio: {sharpe}")


def main() -> int:
    args = parse_args()
    market_data = {ticker: load_stock_data(ticker, start=args.start) for ticker in args.tickers}
    prices = prepare_price_matrix(market_data)
    estimates = estimate_market_inputs(prices)

    max_sharpe = optimize_max_sharpe(
        estimates.expected_returns,
        estimates.covariance_matrix,
        risk_free_rate=args.risk_free_rate,
        cash_weight=args.cash_weight,
        min_weight=args.min_weight,
        max_weight=args.max_weight,
    )
    min_volatility = optimize_minimum_volatility(
        estimates.expected_returns,
        estimates.covariance_matrix,
        risk_free_rate=args.risk_free_rate,
        cash_weight=args.cash_weight,
        min_weight=args.min_weight,
        max_weight=args.max_weight,
    )
    frontier = calculate_efficient_frontier(
        estimates.expected_returns,
        estimates.covariance_matrix,
        risk_free_rate=args.risk_free_rate,
        cash_weight=args.cash_weight,
        min_weight=args.min_weight,
        max_weight=args.max_weight,
        points=args.frontier_points,
    )
    simulation = simulate_portfolio_paths(
        max_sharpe.expected_return,
        max_sharpe.volatility,
        initial_value=args.initial_value,
        simulations=args.simulation_paths,
        seed=args.seed,
    )

    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "tickers": list(estimates.expected_returns.index),
        "price_window": {
            "start": estimates.start_date,
            "end": estimates.end_date,
            "return_observations": estimates.return_observations,
        },
        "assumptions": {
            "periods_per_year": estimates.periods_per_year,
            "risk_free_rate": args.risk_free_rate,
            "cash_weight": args.cash_weight,
            "min_weight": args.min_weight,
            "max_weight": args.max_weight,
            "expected_return_estimator": "annualized arithmetic mean of daily simple returns",
            "covariance_estimator": "annualized sample covariance of daily simple returns",
            "simulation_model": "geometric Brownian motion with constant drift and volatility",
        },
        "annualized_asset_expected_returns": estimates.expected_returns.to_dict(),
        "annualized_covariance": estimates.covariance_matrix.to_dict(),
        "max_sharpe": max_sharpe.to_dict(),
        "minimum_volatility": min_volatility.to_dict(),
        "efficient_frontier": json_records(frontier),
        "monte_carlo": simulation.to_dict(),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    html_path = write_portfolio_analysis_html(
        args.html_output,
        frontier=frontier,
        max_sharpe=max_sharpe,
        min_volatility=min_volatility,
        simulation=simulation,
    )

    print_result("Maximum-Sharpe Portfolio", max_sharpe)
    print()
    print_result("Minimum-Volatility Portfolio", min_volatility)
    print("\nMonte Carlo Terminal Values")
    print(f"  Worst Case (P5): ${simulation.worst_case:,.2f}")
    print(f"  Average Case: ${simulation.average_case:,.2f}")
    print(f"  Best Case (P95): ${simulation.best_case:,.2f}")
    print(f"  Probability of Loss: {simulation.probability_of_loss:.2%}")
    print(f"\nJSON Report: {args.json_output.resolve()}")
    print(f"Interactive Report: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
