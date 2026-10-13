"""Typed HTTP contracts for the QuantAI research dashboard."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.quant.data import normalize_ticker


class PricePoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int


class IndexPoint(BaseModel):
    date: str
    value: float


class MarketInstrument(BaseModel):
    key: str
    name: str
    symbol: str
    latest_price: float
    change: float
    change_percent: float
    as_of: str
    history: list[IndexPoint]
    source: Literal["yfinance", "market-cache"] = "yfinance"
    served_from_cache: bool = False
    cached_at_utc: str | None = None


class UnavailableMarketInstrument(BaseModel):
    key: str
    name: str
    symbol: str
    reason: Literal["provider_unavailable"] = "provider_unavailable"


class MarketOverviewResponse(BaseModel):
    instruments: list[MarketInstrument]
    source: str
    status: Literal["complete", "partial", "unavailable"] = "complete"
    unavailable_instruments: list[UnavailableMarketInstrument] = Field(default_factory=list)
    research_only: bool = True


class RiskMetricsResponse(BaseModel):
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float | None
    maximum_drawdown: float
    value_at_risk: float
    var_confidence_level: float
    start_date: str
    end_date: str
    observations: int


class FundamentalSnapshotResponse(BaseModel):
    source: str = "yfinance"
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    pe_ratio: float | None
    pb_ratio: float | None
    ev_to_ebitda: float | None
    roe: float | None
    profit_margin: float | None
    debt_ratio: float | None
    retrieved_at_utc: str | None


class FactorPeerRankingResponse(BaseModel):
    ticker: str
    rank: int
    pe_ratio: float | None
    pb_ratio: float | None
    ev_to_ebitda: float | None
    momentum_3m: float | None
    momentum_6m: float | None
    momentum_12m: float | None
    roe: float | None
    profit_margin: float | None
    debt_ratio: float | None
    value_score: float
    momentum_score: float
    quality_score: float
    quant_score: float
    value_coverage: float
    momentum_coverage: float
    quality_coverage: float
    data_coverage: float


class FactorScoreResponse(BaseModel):
    value: float
    momentum: float
    quality: float
    total: float
    rank: int
    universe_size: int
    data_coverage: float
    universe: list[str]
    universe_label: str = "US large-cap technology reference universe"
    universe_market: str = "us"
    market_matched: bool = True
    peer_selection_method: str = "market_fallback"
    peer_sector: str | None = None
    peer_market_cap_band: str | None = None
    peer_rankings: list[FactorPeerRankingResponse] = Field(default_factory=list)
    current_snapshot: bool = True


class InstrumentContextResponse(BaseModel):
    market: str
    currency: str
    suggested_benchmark: str


class InstrumentSearchResultResponse(BaseModel):
    symbol: str
    name: str
    exchange: str
    quote_type: str
    market: str
    currency: str


class InstrumentSearchResponse(BaseModel):
    query: str
    results: list[InstrumentSearchResultResponse]
    source: str
    warning: str | None = None


class MarketDataStatusResponse(BaseModel):
    provider: str
    served_from_cache: bool
    cached_at_utc: str | None = None
    last_observation: str
    warning: str | None = None


class MLMetricResponse(BaseModel):
    model: str
    rmse: float
    mae: float
    direction_accuracy: float


class MLExperimentResponse(BaseModel):
    status: str
    ticker: str
    horizon_days: int | None = None
    test_start: str | None = None
    test_end: str | None = None
    test_observations: int | None = None
    models: list[MLMetricResponse] = Field(default_factory=list)
    message: str
    research_only: bool = True


class StockAnalysisResponse(BaseModel):
    ticker: str
    source: str
    instrument: InstrumentContextResponse
    data_status: MarketDataStatusResponse
    prices: list[PricePoint]
    risk: RiskMetricsResponse
    fundamentals: FundamentalSnapshotResponse
    factor_score: FactorScoreResponse
    ml_experiment: MLExperimentResponse
    disclaimer: str


class ExplanationEvidence(BaseModel):
    label: str
    value: str
    interpretation: str


class StockExplanationResponse(BaseModel):
    ticker: str
    summary: str
    risk_level: Literal["Lower", "Moderate", "Elevated"]
    observations: list[str]
    evidence: list[ExplanationEvidence]
    limitations: list[str]
    source: Literal["openai", "deterministic"]
    model: str | None
    provider_message: str
    generated_at_utc: str
    disclaimer: str = (
        "AI explains supplied research data only; it does not provide investment advice."
    )


class PortfolioRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=10)
    start: str = "2015-01-01"
    risk_free_rate: float = Field(default=0.0, gt=-1.0, le=1.0)
    cash_weight: float = Field(default=0.15, ge=0.0, lt=1.0)
    min_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    max_weight: float = Field(default=0.60, gt=0.0, le=1.0)
    frontier_points: int = Field(default=30, ge=5, le=100)
    initial_value: float = Field(default=100_000.0, gt=0.0, le=1_000_000_000.0)
    simulation_paths: int = Field(default=10_000, ge=100, le=20_000)
    seed: int = 42
    backtest_lookback_days: int = Field(default=756, ge=126, le=1_260)
    rebalance_days: int = Field(default=63, ge=21, le=252)
    risk_window_days: int = Field(default=63, ge=21, le=252)
    transaction_cost_bps: float = Field(default=10.0, ge=0.0, le=500.0)
    benchmark: str | None = None
    base_currency: Literal["USD", "CNY", "HKD"] = "USD"
    covariance_estimator: Literal["sample", "oas"] = "oas"

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, values: list[str]) -> list[str]:
        normalized = [normalize_ticker(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("tickers must be unique.")
        return normalized

    @field_validator("benchmark")
    @classmethod
    def validate_benchmark(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else normalize_ticker(value)


class PortfolioRobustnessRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=10)
    start: str = "2015-01-01"
    risk_free_rate: float = Field(default=0.0, gt=-1.0, le=1.0)
    cash_weight: float = Field(default=0.15, ge=0.0, lt=1.0)
    min_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    max_weight: float = Field(default=0.60, gt=0.0, le=1.0)
    initial_value: float = Field(default=100_000.0, gt=0.0, le=1_000_000_000.0)
    transaction_cost_bps: float = Field(default=10.0, ge=0.0, le=500.0)
    benchmark: str | None = None
    base_currency: Literal["USD", "CNY", "HKD"] = "USD"
    covariance_estimator: Literal["sample", "oas"] = "oas"
    lookback_options: list[int] = Field(
        default_factory=lambda: [252, 504, 756], min_length=2, max_length=5
    )
    rebalance_options: list[int] = Field(
        default_factory=lambda: [21, 63, 126], min_length=2, max_length=5
    )

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, values: list[str]) -> list[str]:
        normalized = [normalize_ticker(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("tickers must be unique.")
        return normalized

    @field_validator("benchmark")
    @classmethod
    def validate_benchmark(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else normalize_ticker(value)

    @field_validator("lookback_options")
    @classmethod
    def validate_lookbacks(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("lookback_options must be unique.")
        if any(value < 126 or value > 1_260 for value in values):
            raise ValueError("lookback_options must be between 126 and 1260.")
        return sorted(values)

    @field_validator("rebalance_options")
    @classmethod
    def validate_rebalances(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("rebalance_options must be unique.")
        if any(value < 21 or value > 252 for value in values):
            raise ValueError("rebalance_options must be between 21 and 252.")
        return sorted(values)


class AllocationItem(BaseModel):
    asset: str
    weight: float


class PortfolioSummary(BaseModel):
    expected_return: float
    volatility: float
    sharpe_ratio: float | None


class FrontierPoint(BaseModel):
    expected_return: float
    volatility: float
    sharpe_ratio: float | None


class SimulationSummary(BaseModel):
    initial_value: float
    worst_case: float
    average_case: float
    median_case: float
    best_case: float
    probability_of_loss: float
    simulations: int
    seed: int


class SimulationBandPoint(BaseModel):
    day: int
    lower: float
    median: float
    upper: float


class BacktestStatisticsResponse(BaseModel):
    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float | None
    maximum_drawdown: float


class BacktestPathPointResponse(BaseModel):
    date: str
    strategy_value: float
    benchmark_value: float
    strategy_drawdown: float
    benchmark_drawdown: float
    strategy_rolling_volatility: float | None
    benchmark_rolling_volatility: float | None
    rolling_beta: float | None


class BacktestRiskDiagnosticsResponse(BaseModel):
    downside_deviation: float
    sortino_ratio: float | None
    beta: float | None
    correlation: float | None
    tracking_error: float
    information_ratio: float | None
    longest_drawdown_days: int
    benchmark_longest_drawdown_days: int


class RebalanceEventResponse(BaseModel):
    date: str
    turnover: float
    transaction_cost: float
    weights: dict[str, float]


class BacktestResponse(BaseModel):
    start_date: str
    end_date: str
    benchmark: str
    lookback_days: int
    rebalance_days: int
    risk_window_days: int
    transaction_cost_bps: float
    covariance_estimator: Literal["sample", "oas"]
    total_transaction_cost: float
    strategy: BacktestStatisticsResponse
    benchmark_statistics: BacktestStatisticsResponse
    risk_diagnostics: BacktestRiskDiagnosticsResponse
    path: list[BacktestPathPointResponse]
    rebalances: list[RebalanceEventResponse]
    disclaimer: str


class RobustnessScenarioResponse(BaseModel):
    lookback_days: int
    rebalance_days: int
    cagr: float
    sharpe_ratio: float | None
    maximum_drawdown: float
    excess_cagr: float
    total_transaction_cost: float
    average_turnover: float
    rebalance_count: int


class PortfolioRobustnessResponse(BaseModel):
    start_date: str
    end_date: str
    benchmark: str
    covariance_estimator: Literal["sample", "oas"]
    base_currency: Literal["USD", "CNY", "HKD"]
    benchmark_cagr: float
    lookback_options: list[int]
    rebalance_options: list[int]
    median_cagr: float
    median_sharpe_ratio: float | None
    worst_maximum_drawdown: float
    cagr_dispersion: float
    positive_excess_fraction: float
    scenarios: list[RobustnessScenarioResponse]
    disclaimer: str


class EstimationDiagnosticsResponse(BaseModel):
    covariance_estimator: Literal["sample", "oas"]
    shrinkage_intensity: float | None
    covariance_condition_number: float
    sample_covariance_condition_number: float


class EstimatorComparisonResponse(BaseModel):
    covariance_estimator: Literal["sample", "oas"]
    shrinkage_intensity: float | None
    covariance_condition_number: float
    expected_return: float
    volatility: float
    sharpe_ratio: float | None
    backtest_cagr: float
    backtest_volatility: float
    backtest_sharpe_ratio: float | None
    backtest_maximum_drawdown: float
    average_turnover: float
    total_transaction_cost: float


class PortfolioResponse(BaseModel):
    tickers: list[str]
    base_currency: Literal["USD", "CNY", "HKD"]
    quote_currencies: list[str]
    price_start: str
    price_end: str
    return_observations: int
    covariance_estimator: Literal["sample", "oas"]
    estimation_diagnostics: EstimationDiagnosticsResponse
    estimator_comparison: list[EstimatorComparisonResponse]
    allocation: list[AllocationItem]
    summary: PortfolioSummary
    minimum_volatility: PortfolioSummary
    frontier: list[FrontierPoint]
    simulation: SimulationSummary
    simulation_band: list[SimulationBandPoint]
    backtest: BacktestResponse
    assumptions: list[str]
    disclaimer: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
