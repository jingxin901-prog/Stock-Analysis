"""Time-aware baseline, linear, boosted-tree, and LSTM experiments."""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.quant.ml.features import TimeSeriesSplits


class ModelExperimentError(ValueError):
    """Raised when an experiment cannot be trained or evaluated safely."""


@dataclass(frozen=True)
class PredictionMetrics:
    """Out-of-sample regression and sign-classification metrics."""

    rmse: float
    mae: float
    direction_accuracy: float


@dataclass(frozen=True)
class ModelEvaluation:
    """A model's common-period out-of-sample result."""

    model_name: str
    metrics: PredictionMetrics
    actuals: pd.Series
    predictions: pd.Series
    metadata: dict[str, Any]

    def to_dict(self, *, include_predictions: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "model_name": self.model_name,
            "metrics": asdict(self.metrics),
            "test_observations": len(self.actuals),
            "test_start": self.actuals.index.min().date().isoformat(),
            "test_end": self.actuals.index.max().date().isoformat(),
            "metadata": self.metadata,
        }
        if include_predictions:
            result["predictions"] = [
                {
                    "date": date.date().isoformat(),
                    "actual_return": float(actual),
                    "predicted_return": float(prediction),
                }
                for date, actual, prediction in zip(
                    self.actuals.index, self.actuals, self.predictions, strict=True
                )
            ]
        return result


def calculate_prediction_metrics(
    actuals: pd.Series | np.ndarray,
    predictions: pd.Series | np.ndarray,
) -> PredictionMetrics:
    """Calculate RMSE, MAE, and directional accuracy."""

    actual = np.asarray(actuals, dtype="float64").reshape(-1)
    predicted = np.asarray(predictions, dtype="float64").reshape(-1)
    if actual.shape != predicted.shape or actual.size == 0:
        raise ModelExperimentError("actuals and predictions must have equal nonzero length.")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ModelExperimentError("actuals and predictions must be finite.")

    errors = predicted - actual
    return PredictionMetrics(
        rmse=float(np.sqrt(np.mean(np.square(errors)))),
        mae=float(np.mean(np.abs(errors))),
        direction_accuracy=float(np.mean(np.sign(predicted) == np.sign(actual))),
    )


def run_model_comparison(
    splits: TimeSeriesSplits,
    *,
    lookback: int = 30,
    lstm_epochs: int = 25,
    lstm_patience: int = 5,
    random_seed: int = 42,
) -> dict[str, ModelEvaluation]:
    """Train all requested models and compare them on identical test dates."""

    _validate_splits(splits)
    _validate_positive_integer(lookback, "lookback")
    _validate_positive_integer(lstm_epochs, "lstm_epochs")
    _validate_positive_integer(lstm_patience, "lstm_patience")
    if min(len(splits.X_train), len(splits.X_validation), len(splits.X_test)) < lookback:
        raise ModelExperimentError("Every partition must contain at least lookback observations.")

    common_index = splits.X_test.index[lookback - 1 :]
    actuals = splits.y_test.loc[common_index].astype("float64")
    baseline_predictions = pd.Series(0.0, index=common_index, name="prediction")
    evaluations: dict[str, ModelEvaluation] = {
        "baseline": _build_evaluation(
            "Zero-Return Baseline",
            actuals,
            baseline_predictions,
            {
                "purpose": "Naive benchmark; predicts a zero five-day return.",
                "direction_rule": "Zero represents no direction and does not count as an up move.",
            },
        )
    }
    evaluations["linear_regression"] = train_linear_regression(
        splits, evaluation_index=common_index
    )
    evaluations["xgboost"] = train_xgboost(
        splits, evaluation_index=common_index, random_seed=random_seed
    )
    evaluations["lstm"] = train_lstm(
        splits,
        lookback=lookback,
        epochs=lstm_epochs,
        patience=lstm_patience,
        random_seed=random_seed,
    )
    return evaluations


def train_linear_regression(
    splits: TimeSeriesSplits,
    *,
    evaluation_index: pd.DatetimeIndex | None = None,
) -> ModelEvaluation:
    """Fit a scaled OLS benchmark using the training partition only."""

    _validate_splits(splits)
    index = evaluation_index if evaluation_index is not None else splits.X_test.index
    _validate_evaluation_index(index, splits.X_test.index)

    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("regressor", LinearRegression()),
        ]
    )
    model.fit(splits.X_train, splits.y_train)
    predictions = pd.Series(model.predict(splits.X_test.loc[index]), index=index, name="prediction")
    return _build_evaluation(
        "Linear Regression",
        splits.y_test.loc[index],
        predictions,
        {
            "estimator": "Ordinary least squares",
            "feature_scaling": "StandardScaler fitted on training data only",
        },
    )


def train_xgboost(
    splits: TimeSeriesSplits,
    *,
    evaluation_index: pd.DatetimeIndex | None = None,
    random_seed: int = 42,
) -> ModelEvaluation:
    """Fit a regularized boosted-tree model with validation early stopping."""

    _validate_splits(splits)
    index = evaluation_index if evaluation_index is not None else splits.X_test.index
    _validate_evaluation_index(index, splits.X_test.index)
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise ModelExperimentError(
            "XGBoost is not installed; install the project dependencies first."
        ) from exc

    model = XGBRegressor(
        n_estimators=750,
        learning_rate=0.03,
        max_depth=3,
        min_child_weight=5.0,
        subsample=0.80,
        colsample_bytree=0.80,
        reg_alpha=0.05,
        reg_lambda=1.0,
        objective="reg:squarederror",
        eval_metric="rmse",
        early_stopping_rounds=40,
        random_state=random_seed,
        n_jobs=1,
        tree_method="hist",
    )
    model.fit(
        splits.X_train,
        splits.y_train,
        eval_set=[(splits.X_validation, splits.y_validation)],
        verbose=False,
    )
    predictions = pd.Series(model.predict(splits.X_test.loc[index]), index=index, name="prediction")
    best_iteration = getattr(model, "best_iteration", None)
    return _build_evaluation(
        "XGBoost",
        splits.y_test.loc[index],
        predictions,
        {
            "estimator": "XGBRegressor",
            "early_stopping_validation": True,
            "best_iteration": None if best_iteration is None else int(best_iteration),
            "random_seed": random_seed,
        },
    )


def train_lstm(
    splits: TimeSeriesSplits,
    *,
    lookback: int = 30,
    epochs: int = 25,
    patience: int = 5,
    hidden_size: int = 32,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    random_seed: int = 42,
) -> ModelEvaluation:
    """Fit a compact PyTorch LSTM with training-only scaling."""

    _validate_splits(splits)
    for value, name in (
        (lookback, "lookback"),
        (epochs, "epochs"),
        (patience, "patience"),
        (hidden_size, "hidden_size"),
        (batch_size, "batch_size"),
    ):
        _validate_positive_integer(value, name)
    if not math.isfinite(learning_rate) or learning_rate <= 0.0:
        raise ModelExperimentError("learning_rate must be positive and finite.")
    if min(len(splits.X_train), len(splits.X_validation), len(splits.X_test)) < lookback:
        raise ModelExperimentError("Every partition must contain at least lookback observations.")

    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise ModelExperimentError(
            "PyTorch is not installed; install the project dependencies first."
        ) from exc

    np.random.seed(random_seed)
    torch.manual_seed(random_seed)
    torch.use_deterministic_algorithms(True, warn_only=True)

    feature_scaler = StandardScaler()
    train_features = feature_scaler.fit_transform(splits.X_train)
    validation_features = feature_scaler.transform(splits.X_validation)
    test_features = feature_scaler.transform(splits.X_test)

    target_mean = float(splits.y_train.mean())
    target_scale = float(splits.y_train.std(ddof=0))
    if not math.isfinite(target_scale) or target_scale <= 1e-12:
        target_scale = 1.0
    train_targets = (splits.y_train.to_numpy(dtype="float64") - target_mean) / target_scale
    validation_targets = (
        splits.y_validation.to_numpy(dtype="float64") - target_mean
    ) / target_scale
    test_targets = (splits.y_test.to_numpy(dtype="float64") - target_mean) / target_scale

    train_X, train_y, _ = create_sequences(
        train_features, train_targets, splits.X_train.index, lookback=lookback
    )
    validation_X, validation_y, _ = create_sequences(
        validation_features,
        validation_targets,
        splits.X_validation.index,
        lookback=lookback,
    )
    test_X, _, test_index = create_sequences(
        test_features, test_targets, splits.X_test.index, lookback=lookback
    )

    class LSTMReturnRegressor(nn.Module):
        def __init__(self, input_size: int, state_size: int) -> None:
            super().__init__()
            self.lstm = nn.LSTM(input_size, state_size, batch_first=True)
            self.output = nn.Linear(state_size, 1)

        def forward(self, values: Any) -> Any:
            sequence_output, _ = self.lstm(values)
            return self.output(sequence_output[:, -1, :]).squeeze(-1)

    device = torch.device("cpu")
    model = LSTMReturnRegressor(train_X.shape[2], hidden_size).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    loss_function = nn.MSELoss()
    generator = torch.Generator().manual_seed(random_seed)
    training_loader = DataLoader(
        TensorDataset(
            torch.tensor(train_X, dtype=torch.float32),
            torch.tensor(train_y, dtype=torch.float32),
        ),
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
        num_workers=0,
    )
    validation_X_tensor = torch.tensor(validation_X, dtype=torch.float32, device=device)
    validation_y_tensor = torch.tensor(validation_y, dtype=torch.float32, device=device)

    best_state: dict[str, Any] | None = None
    best_validation_loss = float("inf")
    epochs_without_improvement = 0
    epochs_trained = 0
    for epoch in range(epochs):
        model.train()
        for batch_X, batch_y in training_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            loss = loss_function(model(batch_X), batch_y)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            validation_loss = float(
                loss_function(model(validation_X_tensor), validation_y_tensor).item()
            )
        epochs_trained = epoch + 1
        if validation_loss < best_validation_loss - 1e-8:
            best_validation_loss = validation_loss
            best_state = copy.deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                break

    if best_state is None:
        raise ModelExperimentError("LSTM training did not produce a valid model state.")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        normalized_predictions = (
            model(torch.tensor(test_X, dtype=torch.float32, device=device))
            .cpu()
            .numpy()
            .astype("float64")
        )
    predicted_returns = normalized_predictions * target_scale + target_mean
    predictions = pd.Series(predicted_returns, index=test_index, name="prediction")
    return _build_evaluation(
        "LSTM",
        splits.y_test.loc[test_index],
        predictions,
        {
            "framework": "PyTorch",
            "lookback_days": lookback,
            "hidden_size": hidden_size,
            "epochs_requested": epochs,
            "epochs_trained": epochs_trained,
            "early_stopping_patience": patience,
            "best_validation_loss_scaled": best_validation_loss,
            "feature_scaling": "StandardScaler fitted on training data only",
            "target_scaling": "Training mean and population standard deviation",
            "device": "cpu",
            "random_seed": random_seed,
        },
    )


def create_sequences(
    features: np.ndarray,
    targets: np.ndarray,
    dates: pd.DatetimeIndex,
    *,
    lookback: int,
) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Create sequences ending at each prediction date within one partition."""

    _validate_positive_integer(lookback, "lookback")
    X = np.asarray(features, dtype="float64")
    y = np.asarray(targets, dtype="float64").reshape(-1)
    if X.ndim != 2 or len(X) != len(y) or len(X) != len(dates):
        raise ModelExperimentError("features, targets, and dates must have matching rows.")
    if len(X) < lookback:
        raise ModelExperimentError("Not enough observations for the requested lookback.")
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ModelExperimentError("Sequence inputs must be finite.")

    sequences = np.stack([X[end - lookback + 1 : end + 1] for end in range(lookback - 1, len(X))])
    sequence_targets = y[lookback - 1 :]
    sequence_dates = dates[lookback - 1 :]
    return sequences, sequence_targets, sequence_dates


def comparison_frame(evaluations: dict[str, ModelEvaluation]) -> pd.DataFrame:
    """Return a display-friendly metric comparison ordered by RMSE."""

    rows = [
        {
            "model": evaluation.model_name,
            "rmse": evaluation.metrics.rmse,
            "mae": evaluation.metrics.mae,
            "direction_accuracy": evaluation.metrics.direction_accuracy,
            "test_observations": len(evaluation.actuals),
        }
        for evaluation in evaluations.values()
    ]
    return pd.DataFrame(rows).sort_values("rmse", kind="stable").reset_index(drop=True)


def _build_evaluation(
    model_name: str,
    actuals: pd.Series,
    predictions: pd.Series,
    metadata: dict[str, Any],
) -> ModelEvaluation:
    actual = actuals.astype("float64").rename("actual")
    predicted = predictions.astype("float64").rename("prediction")
    if not actual.index.equals(predicted.index):
        raise ModelExperimentError("Actual and prediction dates must match exactly.")
    metrics = calculate_prediction_metrics(actual, predicted)
    return ModelEvaluation(model_name, metrics, actual, predicted, metadata)


def _validate_splits(splits: TimeSeriesSplits) -> None:
    if not isinstance(splits, TimeSeriesSplits):
        raise ModelExperimentError("splits must be a TimeSeriesSplits instance.")
    frames = (splits.X_train, splits.X_validation, splits.X_test)
    targets = (splits.y_train, splits.y_validation, splits.y_test)
    expected_columns = splits.X_train.columns
    for frame, target in zip(frames, targets, strict=True):
        if frame.empty or target.empty or len(frame) != len(target):
            raise ModelExperimentError("Each partition must contain aligned observations.")
        if not frame.columns.equals(expected_columns):
            raise ModelExperimentError("All partitions must use identical feature columns.")
        if not frame.index.equals(target.index):
            raise ModelExperimentError("Feature and target dates must match in every partition.")
        if not np.isfinite(frame.to_numpy(dtype="float64")).all():
            raise ModelExperimentError("Features must be finite.")
        if not np.isfinite(target.to_numpy(dtype="float64")).all():
            raise ModelExperimentError("Targets must be finite.")
    if not (
        splits.X_train.index.max()
        < splits.X_validation.index.min()
        < splits.X_validation.index.max()
        < splits.X_test.index.min()
    ):
        raise ModelExperimentError("Partitions must be strictly chronological.")


def _validate_evaluation_index(index: pd.DatetimeIndex, available_index: pd.DatetimeIndex) -> None:
    if not isinstance(index, pd.DatetimeIndex) or len(index) == 0:
        raise ModelExperimentError("evaluation_index must contain test dates.")
    if not index.isin(available_index).all():
        raise ModelExperimentError("evaluation_index must be a subset of test dates.")


def _validate_positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ModelExperimentError(f"{name} must be a positive integer.")
