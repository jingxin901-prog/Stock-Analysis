"""Deterministic tests for model evaluation and sequence construction."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
from app.quant.ml.features import TimeSeriesSplits
from app.quant.ml.models import (
    calculate_prediction_metrics,
    create_sequences,
    train_linear_regression,
)


class PredictionMetricTests(unittest.TestCase):
    def test_metrics_have_explicit_return_units_and_direction_rule(self) -> None:
        actual = np.array([0.02, -0.01, 0.00, -0.03])
        predicted = np.array([0.01, 0.02, -0.01, -0.02])

        metrics = calculate_prediction_metrics(actual, predicted)

        expected_errors = predicted - actual
        self.assertAlmostEqual(metrics.rmse, np.sqrt(np.mean(expected_errors**2)))
        self.assertAlmostEqual(metrics.mae, np.mean(np.abs(expected_errors)))
        self.assertEqual(metrics.direction_accuracy, 0.50)


class SequenceTests(unittest.TestCase):
    def test_sequences_end_on_their_prediction_date(self) -> None:
        features = np.arange(20.0).reshape(10, 2)
        targets = np.arange(10.0)
        dates = pd.bdate_range("2024-01-01", periods=10)

        X, y, sequence_dates = create_sequences(features, targets, dates, lookback=4)

        self.assertEqual(X.shape, (7, 4, 2))
        np.testing.assert_array_equal(X[0], features[:4])
        np.testing.assert_array_equal(y, targets[3:])
        self.assertEqual(sequence_dates[0], dates[3])


class LinearRegressionTests(unittest.TestCase):
    def test_linear_model_runs_on_chronological_partitions(self) -> None:
        dates = pd.bdate_range("2024-01-01", periods=90)
        values = np.linspace(-1.0, 1.0, 90)
        features = pd.DataFrame(
            {"x1": values, "x2": np.square(values)}, index=dates, dtype="float64"
        )
        target = pd.Series(0.02 * values - 0.01, index=dates, dtype="float64")
        splits = TimeSeriesSplits(
            X_train=features.iloc[:50],
            y_train=target.iloc[:50],
            X_validation=features.iloc[55:70],
            y_validation=target.iloc[55:70],
            X_test=features.iloc[75:],
            y_test=target.iloc[75:],
            purge_gap=5,
        )

        evaluation = train_linear_regression(splits)

        self.assertLess(evaluation.metrics.rmse, 1e-10)
        self.assertEqual(evaluation.actuals.index.tolist(), dates[75:].tolist())


if __name__ == "__main__":
    unittest.main()
