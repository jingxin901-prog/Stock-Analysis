"""Plotly figures and self-contained HTML export for portfolio research."""

from __future__ import annotations

from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.quant.simulation import MonteCarloResult

from .optimizer import PortfolioResult


def create_efficient_frontier_figure(
    frontier: pd.DataFrame,
    max_sharpe: PortfolioResult,
    min_volatility: PortfolioResult,
) -> go.Figure:
    """Create the interactive mean-variance frontier figure."""

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=frontier["volatility"] * 100.0,
            y=frontier["expected_return"] * 100.0,
            mode="lines+markers",
            name="Efficient Frontier",
            marker={"size": 5, "color": frontier["sharpe_ratio"], "colorscale": "Viridis"},
            customdata=frontier["sharpe_ratio"],
            hovertemplate=(
                "Volatility %{x:.2f}%<br>Return %{y:.2f}%<br>"
                "Sharpe %{customdata:.3f}<extra></extra>"
            ),
        )
    )
    for result, name, color, symbol in (
        (max_sharpe, "Maximum Sharpe", "#14b8a6", "star"),
        (min_volatility, "Minimum Volatility", "#f59e0b", "diamond"),
    ):
        figure.add_trace(
            go.Scatter(
                x=[result.volatility * 100.0],
                y=[result.expected_return * 100.0],
                mode="markers",
                name=name,
                marker={"size": 14, "color": color, "symbol": symbol},
                hovertemplate=(
                    f"{name}<br>Volatility %{{x:.2f}}%<br>Return %{{y:.2f}}%<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        title="Efficient Frontier",
        xaxis_title="Annualized Volatility (%)",
        yaxis_title="Expected Annual Return (%)",
        template="plotly_dark",
        height=560,
    )
    return figure


def create_allocation_figure(result: PortfolioResult) -> go.Figure:
    """Create a bar chart of risky and cash weights."""

    allocation = {**result.weights, "Cash": result.cash_weight}
    figure = go.Figure(
        go.Bar(
            x=list(allocation.keys()),
            y=[weight * 100.0 for weight in allocation.values()],
            marker_color="#38bdf8",
            hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        title="Maximum-Sharpe Allocation",
        xaxis_title="Asset",
        yaxis_title="Portfolio Weight (%)",
        template="plotly_dark",
        height=440,
    )
    return figure


def create_simulation_figure(
    simulation: MonteCarloResult,
    *,
    max_sample_paths: int = 100,
) -> go.Figure:
    """Create sample paths plus 5th/mean/95th percentile trajectories."""

    figure = go.Figure()
    sample_count = min(max_sample_paths, simulation.simulations)
    sample_indices = np.linspace(0, simulation.simulations - 1, num=sample_count, dtype="int64")
    days = np.arange(simulation.days + 1)
    for index in sample_indices:
        figure.add_trace(
            go.Scatter(
                x=days,
                y=simulation.paths[:, index],
                mode="lines",
                line={"color": "rgba(148, 163, 184, 0.10)", "width": 1},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    lower_path = np.quantile(simulation.paths, simulation.lower_percentile, axis=1)
    mean_path = simulation.paths.mean(axis=1)
    upper_path = np.quantile(simulation.paths, simulation.upper_percentile, axis=1)
    for values, name, color in (
        (lower_path, "5th Percentile", "#f87171"),
        (mean_path, "Mean Path", "#38bdf8"),
        (upper_path, "95th Percentile", "#34d399"),
    ):
        figure.add_trace(
            go.Scatter(
                x=days,
                y=values,
                mode="lines",
                name=name,
                line={"color": color, "width": 3},
                hovertemplate="Day %{x}<br>Value $%{y:,.0f}<extra></extra>",
            )
        )
    figure.update_layout(
        title=f"One-Year Monte Carlo Simulation ({simulation.simulations:,} paths)",
        xaxis_title="Trading Day",
        yaxis_title="Portfolio Value",
        template="plotly_dark",
        height=600,
    )
    return figure


def create_terminal_distribution_figure(simulation: MonteCarloResult) -> go.Figure:
    """Create the simulated terminal-value distribution."""

    figure = go.Figure(
        go.Histogram(
            x=simulation.paths[-1],
            nbinsx=60,
            marker_color="#818cf8",
            hovertemplate="Terminal value $%{x:,.0f}<br>Count %{y}<extra></extra>",
        )
    )
    for value, name, color in (
        (simulation.worst_case, "Worst (P5)", "#f87171"),
        (simulation.average_case, "Average", "#38bdf8"),
        (simulation.best_case, "Best (P95)", "#34d399"),
    ):
        figure.add_vline(x=value, line_width=2, line_dash="dash", line_color=color)
        figure.add_annotation(x=value, y=1.03, yref="paper", text=name, showarrow=False)
    figure.update_layout(
        title="Terminal Portfolio Value Distribution",
        xaxis_title="Terminal Value",
        yaxis_title="Simulation Count",
        template="plotly_dark",
        height=500,
    )
    return figure


def write_portfolio_analysis_html(
    output_path: Path,
    *,
    frontier: pd.DataFrame,
    max_sharpe: PortfolioResult,
    min_volatility: PortfolioResult,
    simulation: MonteCarloResult,
) -> Path:
    """Write a self-contained interactive portfolio analysis report."""

    figures = (
        create_efficient_frontier_figure(frontier, max_sharpe, min_volatility),
        create_allocation_figure(max_sharpe),
        create_simulation_figure(simulation),
        create_terminal_distribution_figure(simulation),
    )
    figure_html = []
    for index, figure in enumerate(figures):
        figure_html.append(
            figure.to_html(
                full_html=False,
                include_plotlyjs=index == 0,
                config={"responsive": True, "displaylogo": False},
            )
        )

    summary = (
        f"Expected return {max_sharpe.expected_return:.2%} · "
        f"Volatility {max_sharpe.volatility:.2%} · "
        f"Sharpe {max_sharpe.sharpe_ratio:.3f} · "
        f"Worst/Average/Best terminal values "
        f"${simulation.worst_case:,.0f} / ${simulation.average_case:,.0f} / "
        f"${simulation.best_case:,.0f}"
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>QuantAI Portfolio Analysis</title>
  <style>
    body {{ margin: 0; padding: 32px; background: #020617; color: #e2e8f0;
            font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    main {{ max-width: 1280px; margin: 0 auto; }}
    h1 {{ margin-bottom: 8px; }}
    .summary {{ color: #94a3b8; margin-bottom: 24px; }}
    .panel {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 16px;
              padding: 12px; margin: 18px 0; overflow: hidden; }}
    .disclaimer {{ color: #94a3b8; font-size: 14px; line-height: 1.5; }}
  </style>
</head>
<body><main>
  <h1>QuantAI Portfolio Optimization and Risk Simulation</h1>
  <p class="summary">{escape(summary)}</p>
  {"".join(f'<section class="panel">{item}</section>' for item in figure_html)}
  <p class="disclaimer">Historical estimates and simulated outcomes are model outputs,
  not forecasts or investment recommendations. Monte Carlo paths assume lognormal returns
  with constant drift and volatility and do not represent tail events reliably.</p>
</main></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path.resolve()
