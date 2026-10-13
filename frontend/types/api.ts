export interface IndexPoint {
  date: string;
  value: number;
}

export interface MarketInstrument {
  key: string;
  name: string;
  symbol: string;
  latest_price: number;
  change: number;
  change_percent: number;
  as_of: string;
  history: IndexPoint[];
  source: "yfinance" | "market-cache";
  served_from_cache: boolean;
  cached_at_utc: string | null;
}

export interface UnavailableMarketInstrument {
  key: string;
  name: string;
  symbol: string;
  reason: "provider_unavailable";
}

export interface MarketOverviewResponse {
  instruments: MarketInstrument[];
  source: string;
  status: "complete" | "partial" | "unavailable";
  unavailable_instruments: UnavailableMarketInstrument[];
  research_only: boolean;
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adjusted_close: number;
  volume: number;
}

export interface RiskMetrics {
  annualized_return: number;
  annualized_volatility: number;
  sharpe_ratio: number | null;
  maximum_drawdown: number;
  value_at_risk: number;
  var_confidence_level: number;
  start_date: string;
  end_date: string;
  observations: number;
}

export interface FundamentalSnapshot {
  source?: string;
  company_name?: string | null;
  sector?: string | null;
  industry?: string | null;
  market_cap?: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  ev_to_ebitda: number | null;
  roe: number | null;
  profit_margin: number | null;
  debt_ratio: number | null;
  retrieved_at_utc: string | null;
}

export interface FactorPeerRanking {
  ticker: string;
  rank: number;
  pe_ratio: number | null;
  pb_ratio: number | null;
  ev_to_ebitda: number | null;
  momentum_3m: number | null;
  momentum_6m: number | null;
  momentum_12m: number | null;
  roe: number | null;
  profit_margin: number | null;
  debt_ratio: number | null;
  value_score: number;
  momentum_score: number;
  quality_score: number;
  quant_score: number;
  value_coverage: number;
  momentum_coverage: number;
  quality_coverage: number;
  data_coverage: number;
}

export interface FactorScore {
  value: number;
  momentum: number;
  quality: number;
  total: number;
  rank: number;
  universe_size: number;
  data_coverage: number;
  universe: string[];
  universe_label?: string;
  universe_market?: string;
  market_matched?: boolean;
  peer_selection_method?: string;
  peer_sector?: string | null;
  peer_market_cap_band?: string | null;
  peer_rankings?: FactorPeerRanking[];
  current_snapshot: boolean;
}

export interface InstrumentContext {
  market: string;
  currency: string;
  suggested_benchmark: string;
}

export interface InstrumentSearchResult {
  symbol: string;
  name: string;
  exchange: string;
  quote_type: string;
  market: string;
  currency: string;
}

export interface InstrumentSearchResponse {
  query: string;
  results: InstrumentSearchResult[];
  source: string;
  warning: string | null;
}

export interface MarketDataStatus {
  provider: string;
  served_from_cache: boolean;
  cached_at_utc: string | null;
  last_observation: string;
  warning: string | null;
}

export interface MLMetric {
  model: string;
  rmse: number;
  mae: number;
  direction_accuracy: number;
}

export interface MLExperiment {
  status: string;
  ticker: string;
  horizon_days: number | null;
  test_start: string | null;
  test_end: string | null;
  test_observations: number | null;
  models: MLMetric[];
  message: string;
  research_only: boolean;
}

export interface StockAnalysisResponse {
  ticker: string;
  source: string;
  instrument?: InstrumentContext;
  data_status?: MarketDataStatus;
  prices: PricePoint[];
  risk: RiskMetrics;
  fundamentals: FundamentalSnapshot;
  factor_score: FactorScore;
  ml_experiment: MLExperiment;
  disclaimer: string;
}

export interface ExplanationEvidence {
  label: string;
  value: string;
  interpretation: string;
}

export interface StockExplanationResponse {
  ticker: string;
  summary: string;
  risk_level: "Lower" | "Moderate" | "Elevated";
  observations: string[];
  evidence: ExplanationEvidence[];
  limitations: string[];
  source: "openai" | "deterministic";
  model: string | null;
  provider_message: string;
  generated_at_utc: string;
  disclaimer: string;
}

export interface PortfolioRequest {
  tickers: string[];
  start?: string;
  risk_free_rate?: number;
  cash_weight?: number;
  min_weight?: number;
  max_weight?: number;
  frontier_points?: number;
  initial_value?: number;
  simulation_paths?: number;
  seed?: number;
  backtest_lookback_days?: number;
  rebalance_days?: number;
  risk_window_days?: number;
  transaction_cost_bps?: number;
  benchmark?: string | null;
  base_currency?: "USD" | "CNY" | "HKD";
  covariance_estimator?: "sample" | "oas";
}

export interface PortfolioRobustnessRequest {
  tickers: string[];
  start?: string;
  risk_free_rate?: number;
  cash_weight?: number;
  min_weight?: number;
  max_weight?: number;
  initial_value?: number;
  transaction_cost_bps?: number;
  lookback_options?: number[];
  rebalance_options?: number[];
  benchmark?: string | null;
  base_currency?: "USD" | "CNY" | "HKD";
  covariance_estimator?: "sample" | "oas";
}

export interface BacktestStatistics {
  total_return: number;
  cagr: number;
  annualized_volatility: number;
  sharpe_ratio: number | null;
  maximum_drawdown: number;
}

export interface BacktestPathPoint {
  date: string;
  strategy_value: number;
  benchmark_value: number;
  strategy_drawdown: number;
  benchmark_drawdown: number;
  strategy_rolling_volatility: number | null;
  benchmark_rolling_volatility: number | null;
  rolling_beta: number | null;
}

export interface BacktestRiskDiagnostics {
  downside_deviation: number;
  sortino_ratio: number | null;
  beta: number | null;
  correlation: number | null;
  tracking_error: number;
  information_ratio: number | null;
  longest_drawdown_days: number;
  benchmark_longest_drawdown_days: number;
}

export interface RebalanceEvent {
  date: string;
  turnover: number;
  transaction_cost: number;
  weights: Record<string, number>;
}

export interface RobustnessScenario {
  lookback_days: number;
  rebalance_days: number;
  cagr: number;
  sharpe_ratio: number | null;
  maximum_drawdown: number;
  excess_cagr: number;
  total_transaction_cost: number;
  average_turnover: number;
  rebalance_count: number;
}

export interface PortfolioRobustnessResponse {
  start_date: string;
  end_date: string;
  benchmark: string;
  covariance_estimator: "sample" | "oas";
  base_currency?: "USD" | "CNY" | "HKD";
  benchmark_cagr: number;
  lookback_options: number[];
  rebalance_options: number[];
  median_cagr: number;
  median_sharpe_ratio: number | null;
  worst_maximum_drawdown: number;
  cagr_dispersion: number;
  positive_excess_fraction: number;
  scenarios: RobustnessScenario[];
  disclaimer: string;
}

export interface PortfolioResponse {
  tickers: string[];
  base_currency?: "USD" | "CNY" | "HKD";
  quote_currencies?: string[];
  price_start: string;
  price_end: string;
  return_observations: number;
  covariance_estimator: "sample" | "oas";
  estimation_diagnostics: {
    covariance_estimator: "sample" | "oas";
    shrinkage_intensity: number | null;
    covariance_condition_number: number;
    sample_covariance_condition_number: number;
  };
  estimator_comparison: {
    covariance_estimator: "sample" | "oas";
    shrinkage_intensity: number | null;
    covariance_condition_number: number;
    expected_return: number;
    volatility: number;
    sharpe_ratio: number | null;
    backtest_cagr: number;
    backtest_volatility: number;
    backtest_sharpe_ratio: number | null;
    backtest_maximum_drawdown: number;
    average_turnover: number;
    total_transaction_cost: number;
  }[];
  strategy_comparison: {
    allocation_strategy: "max_sharpe" | "equal_weight" | "risk_parity";
    covariance_estimator: "sample" | "oas" | null;
    cagr: number;
    annualized_volatility: number;
    sharpe_ratio: number | null;
    maximum_drawdown: number;
    average_turnover: number;
    total_transaction_cost: number;
  }[];
  allocation: { asset: string; weight: number }[];
  summary: PortfolioPerformance;
  minimum_volatility: PortfolioPerformance;
  frontier: { expected_return: number; volatility: number; sharpe_ratio: number | null }[];
  simulation: {
    initial_value: number;
    worst_case: number;
    average_case: number;
    median_case: number;
    best_case: number;
    probability_of_loss: number;
    simulations: number;
    seed: number;
  };
  simulation_band: { day: number; lower: number; median: number; upper: number }[];
  backtest: {
    start_date: string;
    end_date: string;
    benchmark: string;
    lookback_days: number;
    rebalance_days: number;
    risk_window_days: number;
    transaction_cost_bps: number;
    covariance_estimator: "sample" | "oas";
    allocation_strategy: "max_sharpe" | "equal_weight" | "risk_parity";
    total_transaction_cost: number;
    strategy: BacktestStatistics;
    benchmark_statistics: BacktestStatistics;
    risk_diagnostics: BacktestRiskDiagnostics;
    path: BacktestPathPoint[];
    rebalances: RebalanceEvent[];
    disclaimer: string;
  };
  assumptions: string[];
  disclaimer: string;
}

export interface PortfolioPerformance {
  expected_return: number;
  volatility: number;
  sharpe_ratio: number | null;
}
