"""Cross-sectional value, momentum, quality, and composite factor scores."""

from __future__ import annotations

import math
from typing import Final

import pandas as pd

from app.quant.data import FundamentalSnapshot

VALUE_COLUMNS: Final = ("pe_ratio", "pb_ratio", "ev_to_ebitda")
MOMENTUM_COLUMNS: Final = ("momentum_3m", "momentum_6m", "momentum_12m")
QUALITY_COLUMNS: Final = ("roe", "profit_margin", "debt_ratio")
FACTOR_COLUMNS: Final = VALUE_COLUMNS + MOMENTUM_COLUMNS + QUALITY_COLUMNS

_LOWER_IS_BETTER: Final = {*VALUE_COLUMNS, "debt_ratio"}
_STRICTLY_POSITIVE: Final = set(VALUE_COLUMNS)
_NONNEGATIVE: Final = {"debt_ratio"}


class FactorModelError(ValueError):
    """Raised when factor inputs cannot be scored safely."""


def calculate_momentum_factors(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
) -> dict[str, float | None]:
    """Calculate trailing 3-, 6-, and 12-calendar-month price returns."""

    price_series = _extract_price_series(prices, price_column=price_column)
    latest_date = price_series.index[-1]
    latest_price = float(price_series.iloc[-1])

    results: dict[str, float | None] = {}
    for months in (3, 6, 12):
        target_date = latest_date - pd.DateOffset(months=months)
        history = price_series.loc[:target_date]
        key = f"momentum_{months}m"
        results[key] = None if history.empty else latest_price / float(history.iloc[-1]) - 1.0
    return results


def build_factor_record(
    fundamentals: FundamentalSnapshot,
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str = "adjusted_close",
) -> dict[str, str | float | None]:
    """Combine one fundamental snapshot with its trailing momentum measures."""

    momentum = calculate_momentum_factors(prices, price_column=price_column)
    return {
        "ticker": fundamentals.ticker,
        "pe_ratio": fundamentals.pe_ratio,
        "pb_ratio": fundamentals.pb_ratio,
        "ev_to_ebitda": fundamentals.ev_to_ebitda,
        **momentum,
        "roe": fundamentals.roe,
        "profit_margin": fundamentals.profit_margin,
        "debt_ratio": fundamentals.debt_ratio,
    }


def score_factor_universe(
    factor_data: pd.DataFrame,
    *,
    winsor_limits: tuple[float, float] = (0.05, 0.95),
    missing_score: float = 50.0,
) -> pd.DataFrame:
    """Score and rank a cross-section of stocks on a 0-100 scale.

    Continuous inputs are winsorized within the supplied cross-section and then
    converted to percentile scores. Missing or economically invalid inputs are
    assigned a neutral component score while remaining visible in coverage.
    """

    _validate_factor_frame(factor_data)
    _validate_scoring_parameters(winsor_limits, missing_score)

    output = factor_data.loc[:, ["ticker", *FACTOR_COLUMNS]].copy()
    output["ticker"] = output["ticker"].astype(str).str.strip().str.upper()
    scoring_values = pd.DataFrame(index=output.index)

    for column in FACTOR_COLUMNS:
        numeric = pd.to_numeric(output[column], errors="coerce").astype("float64")
        numeric = numeric.where(numeric.map(math.isfinite))
        if column in _STRICTLY_POSITIVE:
            numeric = numeric.where(numeric > 0.0)
        elif column in _NONNEGATIVE:
            numeric = numeric.where(numeric >= 0.0)
        output[column] = numeric
        scoring_values[column] = _winsorize(numeric, winsor_limits)

    component_score_columns: list[str] = []
    for column in FACTOR_COLUMNS:
        score_column = f"{column}_score"
        output[score_column] = _percentile_score(
            scoring_values[column],
            higher_is_better=column not in _LOWER_IS_BETTER,
            missing_score=missing_score,
        )
        component_score_columns.append(score_column)

    value_score_columns = [f"{column}_score" for column in VALUE_COLUMNS]
    momentum_score_columns = [f"{column}_score" for column in MOMENTUM_COLUMNS]
    quality_score_columns = [f"{column}_score" for column in QUALITY_COLUMNS]

    output["value_score"] = output[value_score_columns].mean(axis=1)
    output["momentum_score"] = output[momentum_score_columns].mean(axis=1)
    output["quality_score"] = output[quality_score_columns].mean(axis=1)
    output["quant_score"] = output[["value_score", "momentum_score", "quality_score"]].mean(axis=1)

    output["value_coverage"] = scoring_values[list(VALUE_COLUMNS)].notna().mean(axis=1)
    output["momentum_coverage"] = scoring_values[list(MOMENTUM_COLUMNS)].notna().mean(axis=1)
    output["quality_coverage"] = scoring_values[list(QUALITY_COLUMNS)].notna().mean(axis=1)
    output["data_coverage"] = scoring_values.notna().mean(axis=1)

    ordered_indices = output.sort_values(
        ["quant_score", "data_coverage", "ticker"],
        ascending=[False, False, True],
        kind="stable",
    ).index
    ranks = pd.Series(range(1, len(output) + 1), index=ordered_indices, dtype="int64")
    output["rank"] = ranks.reindex(output.index)

    score_columns = [
        *component_score_columns,
        "value_score",
        "momentum_score",
        "quality_score",
        "quant_score",
    ]
    output[score_columns] = output[score_columns].round(2)
    coverage_columns = [
        "value_coverage",
        "momentum_coverage",
        "quality_coverage",
        "data_coverage",
    ]
    output[coverage_columns] = output[coverage_columns].round(4)
    return output.sort_values("rank").reset_index(drop=True)


def _extract_price_series(
    prices: pd.Series | pd.DataFrame,
    *,
    price_column: str,
) -> pd.Series:
    if isinstance(prices, pd.DataFrame):
        if price_column not in prices.columns:
            raise FactorModelError(f"Missing required price column: {price_column}.")
        series = prices[price_column].copy()
    elif isinstance(prices, pd.Series):
        series = prices.copy()
    else:
        raise TypeError("prices must be a pandas Series or DataFrame.")

    if not isinstance(series.index, pd.DatetimeIndex):
        raise FactorModelError("Price data must use a DatetimeIndex.")
    if series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise FactorModelError("Price dates must be unique and sorted in ascending order.")
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.empty or numeric.isna().any() or not numeric.map(math.isfinite).all():
        raise FactorModelError("Price data must contain finite numeric observations.")
    if (numeric <= 0.0).any():
        raise FactorModelError("Prices must be strictly positive.")
    return numeric.astype("float64")


def _winsorize(series: pd.Series, limits: tuple[float, float]) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return series
    lower = float(valid.quantile(limits[0]))
    upper = float(valid.quantile(limits[1]))
    return series.clip(lower=lower, upper=upper)


def _percentile_score(
    series: pd.Series,
    *,
    higher_is_better: bool,
    missing_score: float,
) -> pd.Series:
    valid = series.dropna()
    scores = pd.Series(missing_score, index=series.index, dtype="float64")
    count = len(valid)
    if count == 0:
        return scores
    if count == 1:
        scores.loc[valid.index] = 50.0
        return scores

    ranks = valid.rank(method="average", ascending=True)
    if higher_is_better:
        valid_scores = (ranks - 1.0) / (count - 1.0) * 100.0
    else:
        valid_scores = (count - ranks) / (count - 1.0) * 100.0
    scores.loc[valid.index] = valid_scores
    return scores


def _validate_factor_frame(factor_data: pd.DataFrame) -> None:
    if not isinstance(factor_data, pd.DataFrame):
        raise TypeError("factor_data must be a pandas DataFrame.")
    if factor_data.empty:
        raise FactorModelError("factor_data must not be empty.")
    required = {"ticker", *FACTOR_COLUMNS}
    missing = sorted(required.difference(factor_data.columns))
    if missing:
        raise FactorModelError(f"factor_data is missing columns: {missing}.")
    if factor_data["ticker"].isna().any():
        raise FactorModelError("ticker values must not be missing.")
    normalized_tickers = factor_data["ticker"].astype(str).str.strip().str.upper()
    if normalized_tickers.eq("").any():
        raise FactorModelError("ticker values must not be empty.")
    if normalized_tickers.duplicated().any():
        raise FactorModelError("factor_data must contain one row per ticker.")


def _validate_scoring_parameters(
    winsor_limits: tuple[float, float],
    missing_score: float,
) -> None:
    if len(winsor_limits) != 2:
        raise FactorModelError("winsor_limits must contain lower and upper quantiles.")
    lower, upper = winsor_limits
    if not 0.0 <= lower < upper <= 1.0:
        raise FactorModelError("winsor_limits must satisfy 0 <= lower < upper <= 1.")
    if (
        isinstance(missing_score, bool)
        or not isinstance(missing_score, (int, float))
        or not math.isfinite(missing_score)
        or not 0.0 <= missing_score <= 100.0
    ):
        raise FactorModelError("missing_score must be between 0 and 100.")
