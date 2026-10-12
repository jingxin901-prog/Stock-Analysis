"""Leakage-aware feature engineering for return-prediction experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

DEFAULT_HORIZON: Final = 5
TARGET_COLUMN: Final = "target_return_5d"
POINT_IN_TIME_FUNDAMENTALS: Final = (
    "pe_ratio",
    "pb_ratio",
    "ev_to_ebitda",
    "roe",
    "profit_margin",
    "debt_ratio",
)
_REQUIRED_MARKET_COLUMNS: Final = (
    "open",
    "high",
    "low",
    "adjusted_close",
    "volume",
)


class FeatureEngineeringError(ValueError):
    """Raised when an ML dataset cannot be built without ambiguous inputs."""


@dataclass(frozen=True)
class TimeSeriesSplits:
    """Chronological train, validation, and test partitions."""

    X_train: pd.DataFrame
    y_train: pd.Series
    X_validation: pd.DataFrame
    y_validation: pd.Series
    X_test: pd.DataFrame
    y_test: pd.Series
    purge_gap: int

    @property
    def feature_names(self) -> list[str]:
        return self.X_train.columns.tolist()


def build_ml_dataset(
    market_data: pd.DataFrame,
    *,
    horizon: int = DEFAULT_HORIZON,
    fundamental_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build time-t features and a forward return target.

    ``fundamental_history`` is optional and must be indexed by the date on which
    each observation became available. Values are carried forward, never
    backward. A current fundamental snapshot without availability dates must
    not be supplied because doing so would leak future information into the
    historical sample.
    """

    _validate_market_data(market_data)
    _validate_positive_integer(horizon, "horizon")

    data = market_data.sort_index().copy()
    price = pd.to_numeric(data["adjusted_close"], errors="coerce").astype("float64")
    volume = pd.to_numeric(data["volume"], errors="coerce").astype("float64")
    log_volume = np.log1p(volume)

    features = pd.DataFrame(index=data.index)
    features["return_1d"] = price.pct_change(1, fill_method=None)
    features["return_5d"] = price.pct_change(5, fill_method=None)
    features["return_21d"] = price.pct_change(21, fill_method=None)
    features["volume_change_1d"] = volume.pct_change(1, fill_method=None)

    volume_mean = log_volume.rolling(21, min_periods=21).mean()
    volume_std = log_volume.rolling(21, min_periods=21).std(ddof=1)
    features["volume_zscore_21d"] = (log_volume - volume_mean) / volume_std

    for window in (10, 20, 50):
        moving_average = price.rolling(window, min_periods=window).mean()
        features[f"ma_gap_{window}"] = price / moving_average - 1.0

    features["rsi_14"] = _relative_strength_index(price, window=14) / 100.0

    ema_12 = price.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_26 = price.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    features["macd"] = macd / price
    features["macd_signal"] = macd_signal / price
    features["macd_histogram"] = (macd - macd_signal) / price

    features["volatility_21d"] = features["return_1d"].rolling(21, min_periods=21).std(
        ddof=1
    ) * math.sqrt(252)
    features["intraday_range"] = (
        pd.to_numeric(data["high"], errors="coerce") / pd.to_numeric(data["low"], errors="coerce")
        - 1.0
    )
    features["open_to_adjusted_close"] = price / pd.to_numeric(data["open"], errors="coerce") - 1.0

    point_in_time_columns: list[str] = []
    if fundamental_history is not None:
        point_in_time = _align_point_in_time_fundamentals(
            fundamental_history, target_index=data.index
        )
        point_in_time_columns = point_in_time.columns.tolist()
        features = features.join(point_in_time)

    target_name = f"target_return_{horizon}d"
    target = (price.shift(-horizon) / price - 1.0).rename(target_name)
    dataset = features.join(target)
    dataset = dataset.replace([np.inf, -np.inf], np.nan).dropna(how="any")
    if dataset.empty:
        raise FeatureEngineeringError(
            "Feature construction produced no complete observations; provide a longer history."
        )

    dataset = dataset.astype("float64")
    dataset.index.name = "date"
    dataset.attrs.update(
        {
            "horizon_days": horizon,
            "target_column": target_name,
            "feature_columns": features.columns.tolist(),
            "fundamental_feature_columns": point_in_time_columns,
            "uses_current_fundamental_snapshot": False,
        }
    )
    return dataset


def split_time_series_dataset(
    dataset: pd.DataFrame,
    *,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
    purge_gap: int = DEFAULT_HORIZON,
) -> TimeSeriesSplits:
    """Chronologically split a dataset and purge labels across boundaries."""

    if not isinstance(dataset, pd.DataFrame) or dataset.empty:
        raise FeatureEngineeringError("dataset must be a nonempty DataFrame.")
    if not isinstance(dataset.index, pd.DatetimeIndex):
        raise FeatureEngineeringError("dataset must use a DatetimeIndex.")
    if dataset.index.has_duplicates or not dataset.index.is_monotonic_increasing:
        raise FeatureEngineeringError("dataset dates must be unique and ascending.")
    if not 0.0 < train_fraction < 1.0:
        raise FeatureEngineeringError("train_fraction must be between 0 and 1.")
    if not 0.0 < validation_fraction < 1.0:
        raise FeatureEngineeringError("validation_fraction must be between 0 and 1.")
    if train_fraction + validation_fraction >= 1.0:
        raise FeatureEngineeringError("train and validation fractions must sum to less than 1.")
    if isinstance(purge_gap, bool) or not isinstance(purge_gap, int) or purge_gap < 0:
        raise FeatureEngineeringError("purge_gap must be a nonnegative integer.")

    target_column = str(dataset.attrs.get("target_column", ""))
    if not target_column:
        candidates = [column for column in dataset.columns if column.startswith("target_return_")]
        if len(candidates) != 1:
            raise FeatureEngineeringError("dataset must identify exactly one target column.")
        target_column = candidates[0]
    if target_column not in dataset.columns:
        raise FeatureEngineeringError(f"Target column {target_column!r} is missing.")

    sample_count = len(dataset)
    train_boundary = int(sample_count * train_fraction)
    validation_boundary = int(sample_count * (train_fraction + validation_fraction))
    train_stop = train_boundary - purge_gap
    validation_stop = validation_boundary - purge_gap
    if train_stop <= 0 or validation_stop <= train_boundary or validation_boundary >= sample_count:
        raise FeatureEngineeringError("dataset is too short for the requested split and purge gap.")

    feature_columns = [column for column in dataset.columns if column != target_column]
    X = dataset.loc[:, feature_columns]
    y = dataset[target_column]
    splits = TimeSeriesSplits(
        X_train=X.iloc[:train_stop].copy(),
        y_train=y.iloc[:train_stop].copy(),
        X_validation=X.iloc[train_boundary:validation_stop].copy(),
        y_validation=y.iloc[train_boundary:validation_stop].copy(),
        X_test=X.iloc[validation_boundary:].copy(),
        y_test=y.iloc[validation_boundary:].copy(),
        purge_gap=purge_gap,
    )
    if min(len(splits.X_train), len(splits.X_validation), len(splits.X_test)) == 0:
        raise FeatureEngineeringError("Every time-series partition must contain observations.")
    return splits


def _relative_strength_index(price: pd.Series, *, window: int) -> pd.Series:
    change = price.diff()
    average_gain = change.clip(lower=0.0).rolling(window, min_periods=window).mean()
    average_loss = (-change.clip(upper=0.0)).rolling(window, min_periods=window).mean()
    relative_strength = average_gain / average_loss
    rsi = 100.0 - 100.0 / (1.0 + relative_strength)
    rsi = rsi.mask((average_loss == 0.0) & (average_gain > 0.0), 100.0)
    return rsi.mask((average_loss == 0.0) & (average_gain == 0.0), 50.0)


def _align_point_in_time_fundamentals(
    history: pd.DataFrame, *, target_index: pd.DatetimeIndex
) -> pd.DataFrame:
    if not isinstance(history, pd.DataFrame) or history.empty:
        raise FeatureEngineeringError("fundamental_history must be a nonempty DataFrame.")
    if not isinstance(history.index, pd.DatetimeIndex):
        raise FeatureEngineeringError(
            "fundamental_history must use availability dates as a DatetimeIndex."
        )
    if history.index.has_duplicates:
        raise FeatureEngineeringError("fundamental_history availability dates must be unique.")

    normalized = history.sort_index().copy()
    if normalized.index.tz is not None:
        normalized.index = normalized.index.tz_convert("UTC").tz_localize(None)
    normalized.index = normalized.index.normalize()
    if normalized.index.has_duplicates:
        raise FeatureEngineeringError(
            "fundamental_history contains duplicate normalized availability dates."
        )

    selected: dict[str, pd.Series] = {}
    for column in POINT_IN_TIME_FUNDAMENTALS:
        if column not in normalized.columns:
            continue
        values = pd.to_numeric(normalized[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        if values.notna().any():
            selected[f"fundamental_{column}"] = values
    if not selected:
        raise FeatureEngineeringError("fundamental_history has no usable supported ratio columns.")

    available = pd.DataFrame(selected, index=normalized.index)
    union_index = available.index.union(target_index).sort_values()
    aligned = available.reindex(union_index).ffill().reindex(target_index)
    aligned.index.name = target_index.name
    return aligned


def _validate_market_data(data: pd.DataFrame) -> None:
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise FeatureEngineeringError("market_data must be a nonempty DataFrame.")
    missing = [column for column in _REQUIRED_MARKET_COLUMNS if column not in data.columns]
    if missing:
        raise FeatureEngineeringError(f"market_data is missing columns: {missing}.")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise FeatureEngineeringError("market_data must use a DatetimeIndex.")
    if data.index.has_duplicates:
        raise FeatureEngineeringError("market_data dates must be unique.")


def _validate_positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FeatureEngineeringError(f"{name} must be a positive integer.")
