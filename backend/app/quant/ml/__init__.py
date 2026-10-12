"""Machine-learning research pipeline."""

from app.quant.ml.features import (
    FeatureEngineeringError,
    TimeSeriesSplits,
    build_ml_dataset,
    split_time_series_dataset,
)
from app.quant.ml.models import (
    ModelEvaluation,
    ModelExperimentError,
    PredictionMetrics,
    calculate_prediction_metrics,
    comparison_frame,
    run_model_comparison,
)
from app.quant.ml.visualization import write_model_comparison_report

__all__ = [
    "FeatureEngineeringError",
    "ModelEvaluation",
    "ModelExperimentError",
    "PredictionMetrics",
    "TimeSeriesSplits",
    "build_ml_dataset",
    "calculate_prediction_metrics",
    "comparison_frame",
    "run_model_comparison",
    "split_time_series_dataset",
    "write_model_comparison_report",
]
