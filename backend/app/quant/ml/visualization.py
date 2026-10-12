"""Interactive model-comparison reporting."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.quant.ml.models import ModelEvaluation, comparison_frame


def write_model_comparison_report(
    evaluations: dict[str, ModelEvaluation],
    output_path: str | Path,
    *,
    ticker: str,
    horizon_days: int,
) -> Path:
    """Write a self-contained Plotly report and return its resolved path."""

    if not evaluations:
        raise ValueError("evaluations must not be empty.")
    comparison = comparison_frame(evaluations)
    first = next(iter(evaluations.values()))
    for evaluation in evaluations.values():
        if not evaluation.actuals.index.equals(first.actuals.index):
            raise ValueError("All model evaluations must use identical test dates.")

    colors = ["#94a3b8", "#38bdf8", "#f59e0b", "#a78bfa"]
    figure = make_subplots(
        rows=2,
        cols=3,
        specs=[[{}, {}, {}], [{"colspan": 3}, None, None]],
        subplot_titles=("RMSE", "MAE", "Direction Accuracy", "Out-of-sample returns"),
        vertical_spacing=0.18,
        row_heights=[0.38, 0.62],
    )
    models = comparison["model"].tolist()
    color_map = {model: colors[index % len(colors)] for index, model in enumerate(models)}
    for column, label, col, percent in (
        ("rmse", "Return", 1, False),
        ("mae", "Return", 2, False),
        ("direction_accuracy", "Accuracy", 3, True),
    ):
        values = comparison[column] * (100.0 if percent else 1.0)
        figure.add_trace(
            go.Bar(
                x=models,
                y=values,
                marker_color=[color_map[model] for model in models],
                text=[f"{value:.1f}%" if percent else f"{value:.4f}" for value in values],
                textposition="outside",
                showlegend=False,
                hovertemplate=(
                    "%{x}<br>%{y:.2f}%<extra></extra>"
                    if percent
                    else "%{x}<br>%{y:.5f}<extra></extra>"
                ),
            ),
            row=1,
            col=col,
        )
        figure.update_yaxes(title_text=label, row=1, col=col)

    figure.add_trace(
        go.Scatter(
            x=first.actuals.index,
            y=first.actuals,
            name="Actual",
            line={"color": "#e2e8f0", "width": 2.2},
            hovertemplate="%{x|%Y-%m-%d}<br>Actual %{y:.2%}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    for key, evaluation in evaluations.items():
        if key == "baseline":
            continue
        figure.add_trace(
            go.Scatter(
                x=evaluation.predictions.index,
                y=evaluation.predictions,
                name=evaluation.model_name,
                line={"width": 1.4},
                opacity=0.85,
                hovertemplate=(
                    f"%{{x|%Y-%m-%d}}<br>{evaluation.model_name} %{{y:.2%}}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

    figure.add_hline(y=0.0, line_dash="dot", line_color="#64748b", row=2, col=1)
    figure.update_yaxes(
        title_text=f"Next {horizon_days}-day return", tickformat=".1%", row=2, col=1
    )
    figure.update_xaxes(title_text="Prediction date", row=2, col=1)
    figure.update_layout(
        title={
            "text": (
                f"{ticker.upper()} — {horizon_days}-Day Return Model Experiment"
                "<br><sup>Chronological holdout; all models evaluated on the same dates</sup>"
            ),
            "x": 0.5,
        },
        template="plotly_dark",
        paper_bgcolor="#07111f",
        plot_bgcolor="#0f172a",
        font={"family": "Inter, Arial, sans-serif", "color": "#e2e8f0"},
        height=920,
        margin={"l": 70, "r": 40, "t": 115, "b": 105},
        legend={"orientation": "h", "y": -0.13, "x": 0.5, "xanchor": "center"},
        bargap=0.25,
    )
    figure.add_annotation(
        text=(
            "Research demonstration only. Metrics describe one historical holdout sample; "
            "they do not establish market predictability and are not investment advice."
        ),
        xref="paper",
        yref="paper",
        x=0.5,
        y=-0.20,
        xanchor="center",
        showarrow=False,
        font={"size": 12, "color": "#94a3b8"},
    )

    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(
        destination,
        include_plotlyjs=True,
        full_html=True,
        config={"displaylogo": False, "responsive": True},
    )
    return destination
