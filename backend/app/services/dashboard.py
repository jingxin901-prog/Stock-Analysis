"""Orchestration services for the web dashboard.

Financial formulas remain in ``app.quant``; this module only coordinates data
access, analytical modules, caching, and API-ready result shapes.
"""

from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from app.quant.data import (
    FundamentalDataError,
    FundamentalSnapshot,
    MarketDataError,
    get_instrument_context,
    infer_portfolio_benchmark,
    load_fundamental_data,
    load_stock_data,
    normalize_ticker,
    portfolio_quote_currencies,
    search_instruments,
    select_factor_peers,
)
from app.quant.explainability import ExplanationLocale, generate_stock_explanation
from app.quant.factors import build_factor_record, score_factor_universe
from app.quant.metrics import calculate_financial_metrics
from app.quant.portfolio import (
    PortfolioOptimizationError,
    calculate_efficient_frontier,
    estimate_market_inputs,
    optimize_max_sharpe,
    optimize_minimum_volatility,
    prepare_price_matrix,
    run_backtest_robustness,
    run_walk_forward_backtest,
)
from app.quant.simulation import simulate_portfolio_paths
from app.schemas.dashboard import (
    AllocationItem,
    BacktestPathPointResponse,
    BacktestResponse,
    BacktestRiskDiagnosticsResponse,
    BacktestStatisticsResponse,
    EstimationDiagnosticsResponse,
    EstimatorComparisonResponse,
    FactorPeerRankingResponse,
    FactorScoreResponse,
    FrontierPoint,
    FundamentalSnapshotResponse,
    IndexPoint,
    InstrumentContextResponse,
    InstrumentSearchResponse,
    InstrumentSearchResultResponse,
    MarketDataStatusResponse,
    MarketInstrument,
    MarketOverviewResponse,
    MLExperimentResponse,
    MLMetricResponse,
    PortfolioRequest,
    PortfolioResponse,
    PortfolioRobustnessRequest,
    PortfolioRobustnessResponse,
    PortfolioSummary,
    PricePoint,
    RebalanceEventResponse,
    RiskMetricsResponse,
    RobustnessScenarioResponse,
    SimulationBandPoint,
    SimulationSummary,
    StockAnalysisResponse,
    StockExplanationResponse,
    UnavailableMarketInstrument,
)

MARKET_INSTRUMENTS: Final = (
    ("sp500", "S&P 500", "^GSPC"),
    ("nasdaq", "NASDAQ Composite", "^IXIC"),
    ("vix", "CBOE Volatility Index", "^VIX"),
    ("bitcoin", "Bitcoin / USD", "BTC-USD"),
)
_CACHE_TTL_SECONDS: Final = 600.0
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class PortfolioMarketDataUnavailableError(MarketDataError):
    """Report every unavailable portfolio input in one actionable error."""

    def __init__(
        self,
        unavailable_symbols: list[str],
        *,
        asset_symbols: list[str],
        benchmark_symbol: str | None,
    ) -> None:
        self.unavailable_symbols = tuple(unavailable_symbols)
        self.asset_symbols = tuple(asset_symbols)
        self.benchmark_symbol = benchmark_symbol
        super().__init__(
            "Market data is temporarily unavailable for: "
            f"{', '.join(self.unavailable_symbols)}. Retry later or remove unavailable assets."
        )


def get_market_overview() -> MarketOverviewResponse:
    """Return available market gauges without letting one provider failure abort all."""

    cache_key = "market-overview"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    start = (now - pd.DateOffset(years=1)).date().isoformat()
    loaded: dict[str, MarketInstrument] = {}
    unavailable: list[UnavailableMarketInstrument] = []
    with ThreadPoolExecutor(max_workers=len(MARKET_INSTRUMENTS)) as executor:
        futures = [
            (
                (key, name, symbol),
                executor.submit(_load_market_instrument, key, name, symbol, start),
            )
            for key, name, symbol in MARKET_INSTRUMENTS
        ]
        for (key, name, symbol), future in futures:
            try:
                loaded[key] = future.result()
            except MarketDataError:
                unavailable.append(UnavailableMarketInstrument(key=key, name=name, symbol=symbol))

    instruments = [loaded[key] for key, _, _ in MARKET_INSTRUMENTS if key in loaded]
    sources = {instrument.source for instrument in instruments}
    source = next(iter(sources)) if len(sources) == 1 else "mixed" if sources else "unavailable"
    status = "unavailable" if not instruments else "partial" if unavailable else "complete"
    response = MarketOverviewResponse(
        instruments=instruments,
        unavailable_instruments=unavailable,
        source=source,
        status=status,
    )
    if status == "complete":
        _cache_set(cache_key, response)
    return response


def search_instrument_catalog(query: str, *, limit: int = 8) -> InstrumentSearchResponse:
    """Search global Yahoo Finance instruments with a cached local fallback."""

    cache_key = f"instrument-search:{query.strip().casefold()}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    records, source, warning = search_instruments(query, limit=limit)
    response = InstrumentSearchResponse(
        query=" ".join(query.strip().split()),
        results=[InstrumentSearchResultResponse(**vars(record)) for record in records],
        source=source,
        warning=warning,
    )
    _cache_set(cache_key, response)
    return response


def get_stock_analysis(
    ticker: str,
    *,
    start: str = "2015-01-01",
    peer_tickers: list[str] | None = None,
) -> StockAnalysisResponse:
    """Return prices, risk, current factor score, and saved ML evidence."""

    symbol = normalize_ticker(ticker)
    custom_peers = _normalize_custom_peers(symbol, peer_tickers)
    peer_cache_key = "auto" if custom_peers is None else "|".join(custom_peers)
    cache_key = f"stock-analysis:{symbol}:{start}:{peer_cache_key}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    prices = load_stock_data(symbol, start=start)
    risk = calculate_financial_metrics(prices)
    requested_snapshot = _safe_fundamental_snapshot(symbol)
    instrument = get_instrument_context(symbol)
    automatic_selection = select_factor_peers(
        symbol,
        sector=requested_snapshot.sector,
        market_cap=requested_snapshot.market_cap,
    )
    if custom_peers is None:
        universe = list(automatic_selection.tickers)
        universe_label = automatic_selection.label
        universe_market = automatic_selection.universe_market
        market_matched = automatic_selection.market_matched
        selection_method = automatic_selection.method
    else:
        universe = [symbol, *custom_peers]
        custom_markets = {get_instrument_context(candidate).market for candidate in universe}
        market_matched = custom_markets == {instrument.market}
        universe_label = "Custom peer universe"
        universe_market = instrument.market if market_matched else "custom"
        selection_method = "custom"

    records = [build_factor_record(requested_snapshot, prices)]
    other_tickers = [candidate for candidate in universe if candidate != symbol]
    peer_workers = 1 if instrument.market != "us" else min(6, len(other_tickers))
    with ThreadPoolExecutor(max_workers=peer_workers) as executor:
        peer_records = executor.map(_safe_load_factor_record, other_tickers)
        records.extend(record for record in peer_records if record is not None)
    ranking = score_factor_universe(pd.DataFrame(records))
    row = ranking.loc[ranking["ticker"] == symbol].iloc[0]
    available_universe = ranking["ticker"].astype(str).tolist()

    response = StockAnalysisResponse(
        ticker=symbol,
        source=str(prices.attrs.get("source", "yfinance")),
        instrument=InstrumentContextResponse(
            market=instrument.market,
            currency=instrument.currency,
            suggested_benchmark=instrument.suggested_benchmark,
        ),
        data_status=MarketDataStatusResponse(
            provider="Yahoo Finance",
            served_from_cache=bool(prices.attrs.get("served_from_cache", False)),
            cached_at_utc=prices.attrs.get("cached_at_utc"),
            last_observation=prices.index[-1].date().isoformat(),
            warning=(
                "The live provider request failed. QuantAI is displaying the most recent "
                "locally cached standardized history."
                if prices.attrs.get("served_from_cache", False)
                else None
            ),
        ),
        prices=_price_points(prices),
        risk=RiskMetricsResponse(
            annualized_return=risk.annualized_return,
            annualized_volatility=risk.annualized_volatility,
            sharpe_ratio=risk.sharpe_ratio,
            maximum_drawdown=risk.maximum_drawdown,
            value_at_risk=risk.value_at_risk,
            var_confidence_level=risk.var_confidence_level,
            start_date=risk.start_date,
            end_date=risk.end_date,
            observations=risk.price_observations,
        ),
        fundamentals=FundamentalSnapshotResponse(
            source=requested_snapshot.source,
            company_name=requested_snapshot.company_name,
            sector=requested_snapshot.sector,
            industry=requested_snapshot.industry,
            market_cap=requested_snapshot.market_cap,
            pe_ratio=requested_snapshot.pe_ratio,
            pb_ratio=requested_snapshot.pb_ratio,
            ev_to_ebitda=requested_snapshot.ev_to_ebitda,
            roe=requested_snapshot.roe,
            profit_margin=requested_snapshot.profit_margin,
            debt_ratio=requested_snapshot.debt_ratio,
            retrieved_at_utc=requested_snapshot.retrieved_at_utc,
        ),
        factor_score=FactorScoreResponse(
            value=float(row["value_score"]),
            momentum=float(row["momentum_score"]),
            quality=float(row["quality_score"]),
            total=float(row["quant_score"]),
            rank=int(row["rank"]),
            universe_size=len(ranking),
            data_coverage=float(row["data_coverage"]),
            universe=available_universe,
            universe_label=universe_label,
            universe_market=universe_market,
            market_matched=(market_matched and len(ranking) >= 3),
            peer_selection_method=selection_method,
            peer_sector=automatic_selection.sector,
            peer_market_cap_band=automatic_selection.market_cap_band,
            peer_rankings=_factor_peer_rankings(ranking),
            current_snapshot=requested_snapshot.source == "yfinance",
        ),
        ml_experiment=_load_ml_experiment(symbol),
        disclaimer=(
            "Historical and current-snapshot research only. Results are not forecasts or "
            "investment recommendations."
        ),
    )
    _cache_set(cache_key, response)
    return response


def optimize_portfolio(request: PortfolioRequest) -> PortfolioResponse:
    """Run the existing optimization and simulation modules for an API request."""

    benchmark = request.benchmark or infer_portfolio_benchmark(request.tickers)
    market_data = _load_portfolio_market_data(request.tickers, request.start, benchmark)
    cached_market_symbols = sorted(
        ticker
        for ticker, frame in market_data.items()
        if frame.attrs.get("served_from_cache", False)
    )
    prices = prepare_price_matrix({ticker: market_data[ticker] for ticker in request.tickers})
    estimates_by_method = {
        estimator: estimate_market_inputs(prices, covariance_estimator=estimator)
        for estimator in ("sample", "oas")
    }
    maximum_sharpe_by_method = {
        estimator: optimize_max_sharpe(
            method_estimates.expected_returns,
            method_estimates.covariance_matrix,
            risk_free_rate=request.risk_free_rate,
            cash_weight=request.cash_weight,
            min_weight=request.min_weight,
            max_weight=request.max_weight,
        )
        for estimator, method_estimates in estimates_by_method.items()
    }
    estimates = estimates_by_method[request.covariance_estimator]
    maximum_sharpe = maximum_sharpe_by_method[request.covariance_estimator]
    minimum_volatility = optimize_minimum_volatility(
        estimates.expected_returns,
        estimates.covariance_matrix,
        risk_free_rate=request.risk_free_rate,
        cash_weight=request.cash_weight,
        min_weight=request.min_weight,
        max_weight=request.max_weight,
    )
    frontier = calculate_efficient_frontier(
        estimates.expected_returns,
        estimates.covariance_matrix,
        risk_free_rate=request.risk_free_rate,
        cash_weight=request.cash_weight,
        min_weight=request.min_weight,
        max_weight=request.max_weight,
        points=request.frontier_points,
    )
    simulation = simulate_portfolio_paths(
        maximum_sharpe.expected_return,
        maximum_sharpe.volatility,
        initial_value=request.initial_value,
        simulations=request.simulation_paths,
        seed=request.seed,
    )
    lower, median, upper = np.quantile(simulation.paths, [0.05, 0.50, 0.95], axis=1)
    backtest_lookback_days = _resolve_backtest_lookback(
        prices,
        market_data[benchmark]["adjusted_close"],
        requested=request.backtest_lookback_days,
    )
    backtests_by_method = {
        estimator: run_walk_forward_backtest(
            prices,
            market_data[benchmark]["adjusted_close"],
            benchmark=benchmark,
            initial_value=request.initial_value,
            risk_free_rate=request.risk_free_rate,
            cash_weight=request.cash_weight,
            min_weight=request.min_weight,
            max_weight=request.max_weight,
            lookback_days=backtest_lookback_days,
            rebalance_days=request.rebalance_days,
            risk_window_days=request.risk_window_days,
            transaction_cost_bps=request.transaction_cost_bps,
            covariance_estimator=estimator,
        )
        for estimator in ("sample", "oas")
    }
    backtest = backtests_by_method[request.covariance_estimator]

    allocation = [
        AllocationItem(asset=ticker, weight=weight)
        for ticker, weight in maximum_sharpe.weights.items()
    ]
    if request.cash_weight > 0.0:
        allocation.append(AllocationItem(asset="Cash", weight=request.cash_weight))
    return PortfolioResponse(
        tickers=request.tickers,
        base_currency=request.base_currency,
        quote_currencies=list(portfolio_quote_currencies(request.tickers)),
        price_start=estimates.start_date,
        price_end=estimates.end_date,
        return_observations=estimates.return_observations,
        covariance_estimator=request.covariance_estimator,
        estimation_diagnostics=EstimationDiagnosticsResponse(
            covariance_estimator=request.covariance_estimator,
            shrinkage_intensity=estimates.shrinkage_intensity,
            covariance_condition_number=estimates.covariance_condition_number,
            sample_covariance_condition_number=estimates.sample_covariance_condition_number,
        ),
        estimator_comparison=[
            EstimatorComparisonResponse(
                covariance_estimator=estimator,
                shrinkage_intensity=estimates_by_method[estimator].shrinkage_intensity,
                covariance_condition_number=(
                    estimates_by_method[estimator].covariance_condition_number
                ),
                expected_return=maximum_sharpe_by_method[estimator].expected_return,
                volatility=maximum_sharpe_by_method[estimator].volatility,
                sharpe_ratio=maximum_sharpe_by_method[estimator].sharpe_ratio,
                backtest_cagr=backtests_by_method[estimator].strategy.cagr,
                backtest_volatility=(
                    backtests_by_method[estimator].strategy.annualized_volatility
                ),
                backtest_sharpe_ratio=backtests_by_method[estimator].strategy.sharpe_ratio,
                backtest_maximum_drawdown=(
                    backtests_by_method[estimator].strategy.maximum_drawdown
                ),
                average_turnover=float(
                    np.mean(
                        [event.turnover for event in backtests_by_method[estimator].rebalances]
                    )
                ),
                total_transaction_cost=(
                    backtests_by_method[estimator].total_transaction_cost
                ),
            )
            for estimator in ("sample", "oas")
        ],
        allocation=allocation,
        summary=_portfolio_summary(maximum_sharpe),
        minimum_volatility=_portfolio_summary(minimum_volatility),
        frontier=[
            FrontierPoint(
                expected_return=float(row.expected_return),
                volatility=float(row.volatility),
                sharpe_ratio=(
                    None if not math.isfinite(float(row.sharpe_ratio)) else float(row.sharpe_ratio)
                ),
            )
            for row in frontier.itertuples(index=False)
        ],
        simulation=SimulationSummary(
            initial_value=simulation.initial_value,
            worst_case=simulation.worst_case,
            average_case=simulation.average_case,
            median_case=simulation.median_case,
            best_case=simulation.best_case,
            probability_of_loss=simulation.probability_of_loss,
            simulations=simulation.simulations,
            seed=simulation.seed,
        ),
        simulation_band=[
            SimulationBandPoint(
                day=day,
                lower=float(lower[day]),
                median=float(median[day]),
                upper=float(upper[day]),
            )
            for day in range(simulation.days + 1)
        ],
        backtest=BacktestResponse(
            start_date=backtest.start_date,
            end_date=backtest.end_date,
            benchmark=backtest.benchmark,
            lookback_days=backtest.lookback_days,
            rebalance_days=backtest.rebalance_days,
            risk_window_days=backtest.risk_window_days,
            transaction_cost_bps=backtest.transaction_cost_bps,
            covariance_estimator=backtest.covariance_estimator,
            total_transaction_cost=backtest.total_transaction_cost,
            strategy=BacktestStatisticsResponse(**vars(backtest.strategy)),
            benchmark_statistics=BacktestStatisticsResponse(**vars(backtest.benchmark_statistics)),
            risk_diagnostics=BacktestRiskDiagnosticsResponse(**vars(backtest.risk_diagnostics)),
            path=[BacktestPathPointResponse(**vars(point)) for point in backtest.path],
            rebalances=[RebalanceEventResponse(**vars(event)) for event in backtest.rebalances],
            disclaimer=(
                "Walk-forward historical study using trailing data only, periodic "
                "rebalancing, and explicit transaction costs. It remains hypothetical "
                "and is not evidence of future performance."
            ),
        ),
        assumptions=[
            "Expected returns use the annualized arithmetic mean of daily simple returns.",
            (
                "Covariance uses annualized daily sample covariance."
                if request.covariance_estimator == "sample"
                else "Covariance uses Oracle Approximating Shrinkage toward a scaled "
                "identity target; the shrinkage intensity is estimated from each "
                "available historical window."
            ),
            "Optimization is long-only with explicit cash and per-asset bounds.",
            "Monte Carlo paths use constant-parameter geometric Brownian motion.",
            "Walk-forward weights use trailing observations only and include trading costs.",
            "Native-currency returns are not converted for foreign-exchange movements.",
            *(
                [
                    "Live provider requests failed for these symbols, so locally cached "
                    f"histories were used: {', '.join(cached_market_symbols)}."
                ]
                if cached_market_symbols
                else []
            ),
            *(
                [
                    "The walk-forward lookback was reduced from "
                    f"{request.backtest_lookback_days} to {backtest_lookback_days} trading "
                    "days because the common aligned history was shorter than requested."
                ]
                if backtest_lookback_days != request.backtest_lookback_days
                else []
            ),
        ],
        disclaimer="Conditional historical model output; not a forecast or investment advice.",
    )


def analyze_portfolio_robustness(
    request: PortfolioRobustnessRequest,
) -> PortfolioRobustnessResponse:
    """Evaluate a parameter grid over one common walk-forward period."""

    benchmark = request.benchmark or infer_portfolio_benchmark(request.tickers)
    market_data = _load_portfolio_market_data(request.tickers, request.start, benchmark)
    prices = prepare_price_matrix({ticker: market_data[ticker] for ticker in request.tickers})
    result = run_backtest_robustness(
        prices,
        market_data[benchmark]["adjusted_close"],
        benchmark=benchmark,
        initial_value=request.initial_value,
        risk_free_rate=request.risk_free_rate,
        cash_weight=request.cash_weight,
        min_weight=request.min_weight,
        max_weight=request.max_weight,
        lookback_options=tuple(request.lookback_options),
        rebalance_options=tuple(request.rebalance_options),
        transaction_cost_bps=request.transaction_cost_bps,
        covariance_estimator=request.covariance_estimator,
    )
    return PortfolioRobustnessResponse(
        start_date=result.start_date,
        end_date=result.end_date,
        benchmark=result.benchmark,
        covariance_estimator=result.covariance_estimator,
        base_currency=request.base_currency,
        benchmark_cagr=result.benchmark_cagr,
        lookback_options=result.lookback_options,
        rebalance_options=result.rebalance_options,
        median_cagr=result.median_cagr,
        median_sharpe_ratio=result.median_sharpe_ratio,
        worst_maximum_drawdown=result.worst_maximum_drawdown,
        cagr_dispersion=result.cagr_dispersion,
        positive_excess_fraction=result.positive_excess_fraction,
        scenarios=[RobustnessScenarioResponse(**vars(scenario)) for scenario in result.scenarios],
        disclaimer=(
            "Parameter-grid results share one historical evaluation period, but the "
            "grid and surviving asset universe were still selected with hindsight. "
            "Robustness across these scenarios does not establish future performance."
        ),
    )


def get_stock_explanation(
    ticker: str,
    *,
    start: str = "2015-01-01",
    locale: ExplanationLocale = "en",
    peer_tickers: list[str] | None = None,
) -> StockExplanationResponse:
    """Explain only the server-computed stock analysis evidence."""

    analysis = get_stock_analysis(ticker, start=start, peer_tickers=peer_tickers)
    return generate_stock_explanation(analysis, locale=locale)


def clear_dashboard_cache() -> None:
    """Clear the short-lived in-memory cache, primarily for tests."""

    with _CACHE_LOCK:
        _CACHE.clear()


def _normalize_custom_peers(target: str, peer_tickers: list[str] | None) -> tuple[str, ...] | None:
    if peer_tickers is None:
        return None
    normalized_values = [normalize_ticker(ticker) for ticker in peer_tickers]
    normalized = tuple(dict.fromkeys(ticker for ticker in normalized_values if ticker != target))
    if len(normalized) < 2:
        raise ValueError("A custom factor universe requires at least two peer tickers.")
    if len(normalized) > 9:
        raise ValueError("A custom factor universe supports at most nine peer tickers.")
    return normalized


def _factor_peer_rankings(ranking: pd.DataFrame) -> list[FactorPeerRankingResponse]:
    raw_columns = (
        "pe_ratio",
        "pb_ratio",
        "ev_to_ebitda",
        "momentum_3m",
        "momentum_6m",
        "momentum_12m",
        "roe",
        "profit_margin",
        "debt_ratio",
    )
    score_columns = (
        "value_score",
        "momentum_score",
        "quality_score",
        "quant_score",
        "value_coverage",
        "momentum_coverage",
        "quality_coverage",
        "data_coverage",
    )
    return [
        FactorPeerRankingResponse(
            ticker=str(row["ticker"]),
            rank=int(row["rank"]),
            **{column: _optional_float(row[column]) for column in raw_columns},
            **{column: float(row[column]) for column in score_columns},
        )
        for _, row in ranking.iterrows()
    ]


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _resolve_backtest_lookback(
    price_matrix: pd.DataFrame,
    benchmark_prices: pd.Series,
    *,
    requested: int,
) -> int:
    """Choose a transparent fallback lookback for shorter common histories."""

    aligned = pd.concat(
        [price_matrix.astype("float64"), benchmark_prices.rename("__benchmark__")],
        axis=1,
        join="inner",
    ).dropna()
    available_returns = max(len(aligned) - 1, 0)
    if available_returns > requested:
        return requested

    candidates = (126, 252, 504, 756, 1_260)
    eligible = [lookback for lookback in candidates if lookback < available_returns]
    if not eligible:
        raise PortfolioOptimizationError(
            "The common aligned history must contain more than 126 return observations "
            "for the walk-forward study. Try an earlier start date or a different asset set."
        )
    return max(eligible)


def _load_market_instrument(key: str, name: str, symbol: str, start: str) -> MarketInstrument:
    data = load_stock_data(symbol, start=start)
    if len(data) < 2:
        raise MarketDataError(f"At least two observations are required for {symbol}.")
    latest = float(data["adjusted_close"].iloc[-1])
    previous = float(data["adjusted_close"].iloc[-2])
    change = latest - previous
    return MarketInstrument(
        key=key,
        name=name,
        symbol=symbol,
        latest_price=latest,
        change=change,
        change_percent=change / previous,
        as_of=data.index[-1].date().isoformat(),
        history=[
            IndexPoint(date=date.date().isoformat(), value=float(value))
            for date, value in data["adjusted_close"].items()
        ],
        source=str(data.attrs.get("source", "yfinance")),
        served_from_cache=bool(data.attrs.get("served_from_cache", False)),
        cached_at_utc=data.attrs.get("cached_at_utc"),
    )


def _safe_fundamental_snapshot(ticker: str) -> FundamentalSnapshot:
    try:
        return load_fundamental_data(ticker)
    except FundamentalDataError:
        return FundamentalSnapshot(
            ticker=ticker,
            retrieved_at_utc=datetime.now(UTC).isoformat(),
            pe_ratio=None,
            pb_ratio=None,
            ev_to_ebitda=None,
            roe=None,
            profit_margin=None,
            debt_ratio=None,
            source="unavailable",
        )


def _load_factor_record(ticker: str) -> dict[str, str | float | None]:
    prices = load_stock_data(ticker)
    snapshot = _safe_fundamental_snapshot(ticker)
    return build_factor_record(snapshot, prices)


def _safe_load_factor_record(ticker: str) -> dict[str, str | float | None] | None:
    """Return an optional peer record so one provider failure cannot fail the target."""

    try:
        return _load_factor_record(ticker)
    except MarketDataError:
        return None


def _price_points(data: pd.DataFrame) -> list[PricePoint]:
    return [
        PricePoint(
            date=date.date().isoformat(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            adjusted_close=float(row["adjusted_close"]),
            volume=int(row["volume"]),
        )
        for date, row in data.iterrows()
    ]


def _load_ml_experiment(ticker: str) -> MLExperimentResponse:
    report_paths = (
        _PROJECT_ROOT / "artifacts" / "analysis" / "ml_nvda_report.json",
        _PROJECT_ROOT / "backend" / "app" / "research_results" / "ml_nvda_summary.json",
    )
    report_path = next((path for path in report_paths if path.exists()), None)
    if report_path is None:
        return _unavailable_ml_experiment(ticker)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _unavailable_ml_experiment(ticker)
    if report.get("ticker") != ticker:
        return _unavailable_ml_experiment(ticker)

    comparison = report.get("comparison", [])
    models = [
        MLMetricResponse(
            model=str(item["model"]),
            rmse=float(item["rmse"]),
            mae=float(item["mae"]),
            direction_accuracy=float(item["direction_accuracy"]),
        )
        for item in comparison
    ]
    model_details = report.get("models", {})
    first_model = next(iter(model_details.values()), {})
    design = report.get("experimental_design", {})
    return MLExperimentResponse(
        status="available",
        ticker=ticker,
        horizon_days=design.get("horizon_days"),
        test_start=first_model.get("test_start"),
        test_end=first_model.get("test_end"),
        test_observations=first_model.get("test_observations"),
        models=models,
        message=(
            "Saved historical holdout comparison. It is not a live signal and does not "
            "establish market predictability."
        ),
    )


def _unavailable_ml_experiment(ticker: str) -> MLExperimentResponse:
    return MLExperimentResponse(
        status="not_available",
        ticker=ticker,
        message=(
            "No saved experiment exists for this ticker. Run scripts/run_ml_experiment.py "
            "to create a historical holdout study."
        ),
    )


def _portfolio_summary(result: Any) -> PortfolioSummary:
    return PortfolioSummary(
        expected_return=result.expected_return,
        volatility=result.volatility,
        sharpe_ratio=result.sharpe_ratio,
    )


def _load_portfolio_market_data(
    tickers: list[str], start: str, benchmark: str
) -> dict[str, pd.DataFrame]:
    symbols = list(dict.fromkeys([*tickers, benchmark]))
    cache_key = f"portfolio-market-data:{start}:{','.join(symbols)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    market_data: dict[str, pd.DataFrame] = {}
    unavailable: list[str] = []
    with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as executor:
        futures = {
            symbol: executor.submit(load_stock_data, symbol, start=start) for symbol in symbols
        }
        for symbol in symbols:
            try:
                market_data[symbol] = futures[symbol].result()
            except MarketDataError:
                unavailable.append(symbol)
    if unavailable:
        unavailable_assets = [symbol for symbol in tickers if symbol in unavailable]
        raise PortfolioMarketDataUnavailableError(
            unavailable,
            asset_symbols=unavailable_assets,
            benchmark_symbol=benchmark if benchmark in unavailable else None,
        )
    _cache_set(cache_key, market_data)
    return market_data


def _cache_get(key: str) -> Any | None:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        stored_at, value = item
        if time.monotonic() - stored_at > _CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
