"""Run a leakage-aware five-day return-prediction research experiment."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from app.quant.data import DEFAULT_START_DATE, load_stock_data
from app.quant.ml import (
    build_ml_dataset,
    comparison_frame,
    run_model_comparison,
    split_time_series_dataset,
    write_model_comparison_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare baseline, linear, XGBoost, and LSTM return models."
    )
    parser.add_argument("ticker", nargs="?", default="NVDA")
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--train-fraction", type=float, default=0.60)
    parser.add_argument("--validation-fraction", type=float, default=0.20)
    parser.add_argument("--purge-gap", type=int, default=None)
    parser.add_argument("--lookback", type=int, default=30)
    parser.add_argument("--lstm-epochs", type=int, default=25)
    parser.add_argument("--lstm-patience", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--fundamental-history",
        type=Path,
        help=(
            "Optional point-in-time CSV with an availability_date column. "
            "Current undated snapshots are intentionally unsupported."
        ),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/analysis/ml_nvda_report.json"),
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=Path("outputs/ml_model_comparison.html"),
    )
    return parser.parse_args()


def load_fundamental_history(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    history = pd.read_csv(path)
    if "availability_date" not in history.columns:
        raise ValueError("Fundamental history CSV must contain availability_date.")
    history["availability_date"] = pd.to_datetime(history["availability_date"], errors="raise")
    return history.set_index("availability_date").sort_index()


def split_summary(features: pd.DataFrame, targets: pd.Series) -> dict[str, Any]:
    return {
        "observations": len(features),
        "start": features.index.min().date().isoformat(),
        "end": features.index.max().date().isoformat(),
        "target_mean": float(targets.mean()),
        "target_standard_deviation": float(targets.std(ddof=1)),
    }


def main() -> int:
    args = parse_args()
    purge_gap = args.horizon if args.purge_gap is None else args.purge_gap
    market_data = load_stock_data(args.ticker, start=args.start)
    fundamental_history = load_fundamental_history(args.fundamental_history)
    dataset = build_ml_dataset(
        market_data,
        horizon=args.horizon,
        fundamental_history=fundamental_history,
    )
    splits = split_time_series_dataset(
        dataset,
        train_fraction=args.train_fraction,
        validation_fraction=args.validation_fraction,
        purge_gap=purge_gap,
    )
    evaluations = run_model_comparison(
        splits,
        lookback=args.lookback,
        lstm_epochs=args.lstm_epochs,
        lstm_patience=args.lstm_patience,
        random_seed=args.seed,
    )
    comparison = comparison_frame(evaluations)

    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "ticker": args.ticker.strip().upper(),
        "research_question": f"Prediction of the next {args.horizon}-trading-day simple return",
        "disclaimer": (
            "Historical holdout experiment only; it does not establish market predictability "
            "and is not investment advice."
        ),
        "data": {
            "source": market_data.attrs.get("source", "unknown"),
            "requested_start": args.start,
            "market_observations": len(market_data),
            "dataset_observations": len(dataset),
            "dataset_start": dataset.index.min().date().isoformat(),
            "dataset_end": dataset.index.max().date().isoformat(),
            "feature_names": splits.feature_names,
            "feature_count": len(splits.feature_names),
            "fundamental_features": dataset.attrs["fundamental_feature_columns"],
            "current_fundamental_snapshot_excluded": True,
        },
        "experimental_design": {
            "horizon_days": args.horizon,
            "train_fraction": args.train_fraction,
            "validation_fraction": args.validation_fraction,
            "purge_gap": purge_gap,
            "lstm_lookback_days": args.lookback,
            "random_seed": args.seed,
            "shuffle_across_time": False,
            "common_test_period": True,
            "train": split_summary(splits.X_train, splits.y_train),
            "validation": split_summary(splits.X_validation, splits.y_validation),
            "test": split_summary(splits.X_test, splits.y_test),
        },
        "comparison": comparison.to_dict(orient="records"),
        "models": {
            key: evaluation.to_dict(include_predictions=True)
            for key, evaluation in evaluations.items()
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    html_path = write_model_comparison_report(
        evaluations,
        args.html_output,
        ticker=args.ticker,
        horizon_days=args.horizon,
    )

    display = comparison.copy()
    display["RMSE"] = display.pop("rmse").map(lambda value: f"{value:.5f}")
    display["MAE"] = display.pop("mae").map(lambda value: f"{value:.5f}")
    display["Direction Accuracy"] = display.pop("direction_accuracy").map(
        lambda value: f"{value:.2%}"
    )
    display = display.rename(columns={"model": "Model", "test_observations": "Test Observations"})
    print(f"{args.ticker.upper()} next-{args.horizon}-day return experiment")
    print(display.to_string(index=False))
    print("\nCurrent fundamental snapshot excluded to prevent look-ahead bias.")
    print(f"JSON Report: {args.json_output.resolve()}")
    print(f"Interactive Report: {html_path}")
    print("Research demonstration only; not investment advice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
