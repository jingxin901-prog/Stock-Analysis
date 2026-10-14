"use client";

import type { Data } from "plotly.js";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { PlotlyChart } from "@/components/plotly-chart";
import { ErrorBanner, LoadingState, MetricCard, Panel, ResearchNotice } from "@/components/ui";
import {
  analyzePortfolioRobustness,
  getApiErrorMessage,
  optimizePortfolio,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { copyText, downloadCsv, downloadJson, replaceQuery } from "@/lib/research-tools";
import type { PortfolioResponse, PortfolioRobustnessResponse } from "@/types/api";

function percent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function currency(value: number, locale: string, currencyCode: string) {
  return new Intl.NumberFormat(locale, { style: "currency", currency: currencyCode, maximumFractionDigits: 0 }).format(value);
}

function diagnosticNumber(value: number) {
  return value >= 1_000_000 ? value.toExponential(2) : value.toFixed(1);
}

function bootstrapValue(value: number | null, format: "percent" | "ratio") {
  if (value === null) return "N/A";
  return format === "percent" ? percent(value) : value.toFixed(3);
}

const bootstrapMetrics = [
  { key: "cagr", label: "portfolio.bootstrapCagr", format: "percent" },
  { key: "annualized_volatility", label: "portfolio.bootstrapVolatility", format: "percent" },
  { key: "sharpe_ratio", label: "portfolio.bootstrapSharpe", format: "ratio" },
  { key: "maximum_drawdown", label: "portfolio.bootstrapDrawdown", format: "percent" },
] as const;

function inferQuoteCurrencies(tickers: string[]) {
  return Array.from(new Set(tickers.map((ticker) => {
    if (ticker.endsWith(".SS") || ticker.endsWith(".SZ")) return "CNY";
    if (ticker.endsWith(".HK")) return "HKD";
    return "USD";
  }))).sort();
}

const assumptionKeys = [
  "portfolio.assumption1",
  "portfolio.assumption2",
  "portfolio.assumption3",
  "portfolio.assumption4",
  "portfolio.assumption5",
  "portfolio.assumption6",
] as const;

const researchPresets = [
  { key: "portfolio.presetMegaCap", tickers: "AAPL, MSFT, NVDA, GOOGL", benchmark: "SPY", currency: "USD" },
  { key: "portfolio.presetCrossSector", tickers: "AAPL, MSFT, JPM, JNJ, XOM", benchmark: "SPY", currency: "USD" },
  { key: "portfolio.presetChinaA", tickers: "600519.SS, 000858.SZ, 300750.SZ, 601318.SS", benchmark: "000001.SS", currency: "CNY" },
  { key: "portfolio.presetHongKong", tickers: "0700.HK, 9988.HK, 3690.HK, 1299.HK", benchmark: "^HSI", currency: "HKD" },
  { key: "portfolio.presetVolatility", tickers: "AAPL, NVDA, TSLA, JNJ", benchmark: "SPY", currency: "USD" },
] as const;

export default function PortfolioOptimizerPage() {
  const [tickers, setTickers] = useState("AAPL, MSFT, NVDA, TSLA");
  const [cashWeight, setCashWeight] = useState("15");
  const [maxWeight, setMaxWeight] = useState("60");
  const [initialValue, setInitialValue] = useState("100000");
  const [lookbackDays, setLookbackDays] = useState("756");
  const [rebalanceDays, setRebalanceDays] = useState("63");
  const [riskWindowDays, setRiskWindowDays] = useState("63");
  const [transactionCostBps, setTransactionCostBps] = useState("10");
  const [benchmark, setBenchmark] = useState("AUTO");
  const [baseCurrency, setBaseCurrency] = useState<"USD" | "CNY" | "HKD">("USD");
  const [covarianceEstimator, setCovarianceEstimator] = useState<"sample" | "oas">("oas");
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [robustnessData, setRobustnessData] = useState<PortfolioRobustnessResponse | null>(null);
  const [robustnessLoading, setRobustnessLoading] = useState(false);
  const [robustnessError, setRobustnessError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<"common.linkCopied" | "portfolio.exported" | null>(null);
  const { locale, t } = useI18n();
  const numberLocale = locale === "zh" ? "zh-CN" : "en-US";
  const resolvedBaseCurrency = data?.base_currency ?? baseCurrency;
  const resolvedQuoteCurrencies = data?.quote_currencies ?? inferQuoteCurrencies(data?.tickers ?? []);
  const resolvedRobustnessCurrency = robustnessData?.base_currency ?? resolvedBaseCurrency;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const savedTickers = params.get("tickers");
    const savedCash = params.get("cash");
    const savedMax = params.get("max");
    const savedValue = params.get("value");
    const savedLookback = params.get("lookback");
    const savedRebalance = params.get("rebalance");
    const savedRiskWindow = params.get("risk");
    const savedCosts = params.get("costs");
    const savedBenchmark = params.get("benchmark");
    const savedCurrency = params.get("currency");
    const savedEstimator = params.get("estimator");
    const frame = window.requestAnimationFrame(() => {
      if (savedTickers) setTickers(savedTickers.split("|").join(", "));
      if (savedCash) setCashWeight(savedCash);
      if (savedMax) setMaxWeight(savedMax);
      if (savedValue) setInitialValue(savedValue);
      if (savedLookback) setLookbackDays(savedLookback);
      if (savedRebalance) setRebalanceDays(savedRebalance);
      if (savedRiskWindow) setRiskWindowDays(savedRiskWindow);
      if (savedCosts) setTransactionCostBps(savedCosts);
      if (savedBenchmark) setBenchmark(savedBenchmark);
      if (savedCurrency === "USD" || savedCurrency === "CNY" || savedCurrency === "HKD") {
        setBaseCurrency(savedCurrency);
      }
      if (savedEstimator === "sample" || savedEstimator === "oas") {
        setCovarianceEstimator(savedEstimator);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  function scenarioUrl(
    symbols: string[],
    cash: number,
    maximum: number,
    value: number,
    lookback: number,
    rebalance: number,
    riskWindow: number,
    costs: number,
    comparisonBenchmark: string,
    displayCurrency: string,
    estimator: "sample" | "oas",
  ) {
    const params = new URLSearchParams();
    params.set("tickers", symbols.join("|"));
    params.set("cash", String(cash));
    params.set("max", String(maximum));
    params.set("value", String(value));
    params.set("lookback", String(lookback));
    params.set("rebalance", String(rebalance));
    params.set("risk", String(riskWindow));
    params.set("costs", String(costs));
    params.set("benchmark", comparisonBenchmark);
    params.set("currency", displayCurrency);
    params.set("estimator", estimator);
    return replaceQuery(params);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setRobustnessData(null);
    setRobustnessError(null);
    const symbols = tickers
      .split(",")
      .map((ticker) => ticker.trim().toUpperCase())
      .filter((ticker, index, items) => ticker && items.indexOf(ticker) === index);
    const cashPercent = Number(cashWeight);
    const maximumPercent = Number(maxWeight);
    const portfolioValue = Number(initialValue);
    const lookback = Number(lookbackDays);
    const rebalance = Number(rebalanceDays);
    const riskWindow = Number(riskWindowDays);
    const costs = Number(transactionCostBps);
    const comparisonBenchmark = benchmark.trim().toUpperCase() || "AUTO";
    if (symbols.length < 2) {
      setError(t("portfolio.validationTickers"));
      setLoading(false);
      return;
    }
    if (
      !Number.isFinite(cashPercent) || cashPercent < 0 || cashPercent >= 100
      || !Number.isFinite(maximumPercent) || maximumPercent <= 0 || maximumPercent > 100
      || !Number.isFinite(portfolioValue) || portfolioValue <= 0
      || !Number.isInteger(lookback) || lookback < 126 || lookback > 1_260
      || !Number.isInteger(rebalance) || rebalance < 21 || rebalance > 252
      || !Number.isInteger(riskWindow) || riskWindow < 21 || riskWindow > 252
      || !Number.isFinite(costs) || costs < 0 || costs > 500
    ) {
      setError(t("portfolio.validationNumbers"));
      setLoading(false);
      return;
    }
    if (symbols.length * (maximumPercent / 100) + 1e-9 < 1 - (cashPercent / 100)) {
      setError(t("portfolio.validationFeasibility"));
      setLoading(false);
      return;
    }
    try {
      const response = await optimizePortfolio({
        tickers: symbols,
        cash_weight: cashPercent / 100,
        max_weight: maximumPercent / 100,
        initial_value: portfolioValue,
        simulation_paths: 10_000,
        seed: 42,
        backtest_lookback_days: lookback,
        rebalance_days: rebalance,
        risk_window_days: riskWindow,
        transaction_cost_bps: costs,
        benchmark: comparisonBenchmark === "AUTO" ? null : comparisonBenchmark,
        base_currency: baseCurrency,
        covariance_estimator: covarianceEstimator,
      });
      setData(response);
      scenarioUrl(
        symbols,
        cashPercent,
        maximumPercent,
        portfolioValue,
        lookback,
        rebalance,
        riskWindow,
        costs,
        comparisonBenchmark,
        baseCurrency,
        covarianceEstimator,
      );
    } catch (reason: unknown) {
      setError(getApiErrorMessage(reason, t));
    } finally {
      setLoading(false);
    }
  }

  async function copyScenarioLink() {
    const symbols = data?.tickers ?? tickers.split(",").map((ticker) => ticker.trim().toUpperCase()).filter(Boolean);
    const url = scenarioUrl(
      symbols,
      Number(cashWeight),
      Number(maxWeight),
      Number(initialValue),
      Number(lookbackDays),
      Number(rebalanceDays),
      Number(riskWindowDays),
      Number(transactionCostBps),
      benchmark.trim().toUpperCase() || "AUTO",
      baseCurrency,
      covarianceEstimator,
    );
    await copyText(url);
    setActionMessage("common.linkCopied");
  }

  function exportAllocation() {
    if (!data) return;
    downloadCsv(
      `quantai-allocation-${data.price_end}.csv`,
      ["asset", "weight", `notional_${resolvedBaseCurrency.toLowerCase()}`],
      data.allocation.map((item) => [
        item.asset,
        item.weight,
        item.weight * data.simulation.initial_value,
      ]),
    );
    setActionMessage("portfolio.exported");
  }

  function exportResult() {
    if (!data) return;
    downloadJson(`quantai-portfolio-research-${data.price_end}.json`, {
      exported_at_utc: new Date().toISOString(),
      methodology: "QuantAI constrained historical portfolio research",
      inputs: {
        tickers: data.tickers,
        cash_weight: Number(cashWeight) / 100,
        max_weight: Number(maxWeight) / 100,
        initial_value: Number(initialValue),
        simulation_paths: 10_000,
        seed: 42,
        backtest_lookback_days: Number(lookbackDays),
        rebalance_days: Number(rebalanceDays),
        risk_window_days: Number(riskWindowDays),
        transaction_cost_bps: Number(transactionCostBps),
        benchmark: data.backtest.benchmark,
        base_currency: resolvedBaseCurrency,
        covariance_estimator: data.covariance_estimator,
      },
      result: data,
    });
    setActionMessage("portfolio.exported");
  }

  function exportBacktest() {
    if (!data) return;
    downloadCsv(
      `quantai-walk-forward-${data.backtest.end_date}.csv`,
      [
        "date",
        "strategy_value",
        "benchmark_value",
        "strategy_drawdown",
        "benchmark_drawdown",
        "strategy_rolling_volatility",
        "benchmark_rolling_volatility",
        "rolling_beta",
      ],
      data.backtest.path.map((point) => [
        point.date,
        point.strategy_value,
        point.benchmark_value,
        point.strategy_drawdown,
        point.benchmark_drawdown,
        point.strategy_rolling_volatility,
        point.benchmark_rolling_volatility,
        point.rolling_beta,
      ]),
    );
    setActionMessage("portfolio.exported");
  }

  async function runRobustnessAnalysis() {
    if (!data) return;
    setRobustnessLoading(true);
    setRobustnessError(null);
    try {
      const response = await analyzePortfolioRobustness({
        tickers: data.tickers,
        cash_weight: Number(cashWeight) / 100,
        max_weight: Number(maxWeight) / 100,
        initial_value: Number(initialValue),
        transaction_cost_bps: Number(transactionCostBps),
        lookback_options: [252, 504, 756],
        rebalance_options: [21, 63, 126],
        benchmark: data.backtest.benchmark,
        base_currency: resolvedBaseCurrency,
        covariance_estimator: data.covariance_estimator,
      });
      setRobustnessData(response);
    } catch (reason: unknown) {
      setRobustnessError(getApiErrorMessage(reason, t));
    } finally {
      setRobustnessLoading(false);
    }
  }

  function exportRobustness() {
    if (!robustnessData) return;
    downloadCsv(
      `quantai-parameter-robustness-${robustnessData.end_date}.csv`,
      [
        "lookback_days",
        "rebalance_days",
        "cagr",
        "excess_cagr",
        "sharpe_ratio",
        "maximum_drawdown",
        "average_turnover",
        "total_transaction_cost",
        "rebalance_count",
      ],
      robustnessData.scenarios.map((scenario) => [
        scenario.lookback_days,
        scenario.rebalance_days,
        scenario.cagr,
        scenario.excess_cagr,
        scenario.sharpe_ratio,
        scenario.maximum_drawdown,
        scenario.average_turnover,
        scenario.total_transaction_cost,
        scenario.rebalance_count,
      ]),
    );
    setActionMessage("portfolio.exported");
  }

  const allocationChart = useMemo<Data[]>(() => data ? [{
    type: "pie",
    labels: data.allocation.map((item) => item.asset === "Cash" ? t("portfolio.cash") : item.asset),
    values: data.allocation.map((item) => item.weight),
    hole: 0.68,
    textinfo: "label+percent",
    textposition: "outside",
    marker: { colors: ["#eaa145", "#4f8fca", "#9871bb", "#6f7d90", "#2e9a70", "#d75a6c"] },
    hovertemplate: "%{label}<br>%{percent}<extra></extra>",
  }] : [], [data, t]);

  const frontierChart = useMemo<Data[]>(() => data ? [
    {
      type: "scatter",
      mode: "lines+markers",
      name: t("portfolio.frontierTrace"),
      x: data.frontier.map((point) => point.volatility * 100),
      y: data.frontier.map((point) => point.expected_return * 100),
      marker: { color: data.frontier.map((point) => point.sharpe_ratio ?? 0), colorscale: "Cividis", size: 7, showscale: true, colorbar: { title: { text: "Sharpe" }, thickness: 9 } },
      line: { color: "#d6933e", width: 1.5 },
      hovertemplate: `${t("portfolio.volatilityAxis")} %{x:.2f}%<br>${t("portfolio.returnAxis")} %{y:.2f}%<extra></extra>`,
    },
    {
      type: "scatter",
      mode: "markers",
      name: t("portfolio.maxSharpeTrace"),
      x: [data.summary.volatility * 100],
      y: [data.summary.expected_return * 100],
      marker: { color: "#5da1de", size: 13, symbol: "diamond", line: { color: "#d8e9f8", width: 1 } },
    },
  ] : [], [data, t]);

  const simulationChart = useMemo<Data[]>(() => data ? [
    {
      type: "scatter", mode: "lines", name: t("portfolio.upper"),
      x: data.simulation_band.map((point) => point.day), y: data.simulation_band.map((point) => point.upper),
      line: { color: "rgba(56,189,248,.18)", width: 1 }, hoverinfo: "skip",
    },
    {
      type: "scatter", mode: "lines", name: t("portfolio.band"),
      x: data.simulation_band.map((point) => point.day), y: data.simulation_band.map((point) => point.lower),
      line: { color: "rgba(56,189,248,.18)", width: 1 }, fill: "tonexty", fillcolor: "rgba(56,189,248,.10)",
      hovertemplate: `${t("portfolio.dayAxis")} %{x}<br>P5 ${resolvedBaseCurrency} %{y:,.0f}<extra></extra>`,
    },
    {
      type: "scatter", mode: "lines", name: t("portfolio.median"),
      x: data.simulation_band.map((point) => point.day), y: data.simulation_band.map((point) => point.median),
      line: { color: "#eaa145", width: 2 }, hovertemplate: `${t("portfolio.dayAxis")} %{x}<br>${t("portfolio.median")} ${resolvedBaseCurrency} %{y:,.0f}<extra></extra>`,
    },
  ] : [], [data, resolvedBaseCurrency, t]);

  const backtestPathChart = useMemo<Data[]>(() => data?.backtest ? [
    {
      type: "scatter",
      mode: "lines",
      name: t("portfolio.strategyTrace"),
      x: data.backtest.path.map((point) => point.date),
      y: data.backtest.path.map((point) => point.strategy_value),
      line: { color: "#eaa145", width: 2.2 },
      hovertemplate: `%{x}<br>${resolvedBaseCurrency} %{y:,.0f}<extra>%{fullData.name}</extra>`,
    },
    {
      type: "scatter",
      mode: "lines",
      name: t("portfolio.benchmarkTrace", { benchmark: data.backtest.benchmark }),
      x: data.backtest.path.map((point) => point.date),
      y: data.backtest.path.map((point) => point.benchmark_value),
      line: { color: "#78909c", width: 1.7, dash: "dot" },
      hovertemplate: `%{x}<br>${resolvedBaseCurrency} %{y:,.0f}<extra>%{fullData.name}</extra>`,
    },
  ] : [], [data, resolvedBaseCurrency, t]);

  const backtestDrawdownChart = useMemo<Data[]>(() => data?.backtest ? [
    {
      type: "scatter",
      mode: "lines",
      name: t("portfolio.strategyTrace"),
      x: data.backtest.path.map((point) => point.date),
      y: data.backtest.path.map((point) => point.strategy_drawdown * 100),
      line: { color: "#c4475d", width: 1.8 },
      fill: "tozeroy",
      fillcolor: "rgba(196,71,93,.08)",
      hovertemplate: "%{x}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
    },
    {
      type: "scatter",
      mode: "lines",
      name: t("portfolio.benchmarkTrace", { benchmark: data.backtest.benchmark }),
      x: data.backtest.path.map((point) => point.date),
      y: data.backtest.path.map((point) => point.benchmark_drawdown * 100),
      line: { color: "#78909c", width: 1.3, dash: "dot" },
      hovertemplate: "%{x}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
    },
  ] : [], [data, t]);

  const rollingRiskChart = useMemo<Data[]>(() => data?.backtest?.risk_diagnostics ? [
    {
      type: "scatter",
      mode: "lines",
      name: t("portfolio.strategyRollingVolatility"),
      x: data.backtest.path.map((point) => point.date),
      y: data.backtest.path.map((point) => point.strategy_rolling_volatility === null ? null : point.strategy_rolling_volatility * 100),
      line: { color: "#c4475d", width: 1.8 },
      hovertemplate: "%{x}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
    },
    {
      type: "scatter",
      mode: "lines",
      name: t("portfolio.benchmarkRollingVolatility", { benchmark: data.backtest.benchmark }),
      x: data.backtest.path.map((point) => point.date),
      y: data.backtest.path.map((point) => point.benchmark_rolling_volatility === null ? null : point.benchmark_rolling_volatility * 100),
      line: { color: "#78909c", width: 1.3, dash: "dot" },
      hovertemplate: "%{x}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
    },
    {
      type: "scatter",
      mode: "lines",
      name: t("portfolio.rollingBeta"),
      x: data.backtest.path.map((point) => point.date),
      y: data.backtest.path.map((point) => point.rolling_beta),
      yaxis: "y2",
      line: { color: "#b7791f", width: 1.4 },
      hovertemplate: "%{x}<br>Beta %{y:.2f}<extra>%{fullData.name}</extra>",
    },
  ] : [], [data, t]);

  const robustnessHeatmap = useMemo<Data[]>(() => robustnessData ? [{
    type: "heatmap",
    x: robustnessData.rebalance_options.map(String),
    y: robustnessData.lookback_options.map(String),
    z: robustnessData.lookback_options.map((lookback) =>
      robustnessData.rebalance_options.map((rebalance) =>
        (robustnessData.scenarios.find(
          (scenario) => scenario.lookback_days === lookback && scenario.rebalance_days === rebalance,
        )?.cagr ?? 0) * 100,
      ),
    ),
    colorscale: [
      [0, "#f3d6dc"],
      [0.5, "#f7f5ea"],
      [1, "#2eb67d"],
    ],
    colorbar: { title: { text: "CAGR %" }, thickness: 10 },
    hovertemplate: `${t("portfolio.lookbackAxis")} %{y}<br>${t("portfolio.rebalanceAxis")} %{x}<br>CAGR %{z:.2f}%<extra></extra>`,
  }] : [], [robustnessData, t]);

  return (
    <>
      <PageHeader
        eyebrow={t("portfolio.eyebrow")}
        title={t("portfolio.title")}
        description={t("portfolio.description")}
      />
      <Panel title={t("portfolio.configTitle")} eyebrow={t("portfolio.configEyebrow")}>
        <div className="preset-row">
          <span className="toolbar-label">{t("portfolio.presets")}</span>
          {researchPresets.map((preset) => (
            <button
              className="preset-button"
              key={preset.key}
              onClick={() => {
                setTickers(preset.tickers);
                setBenchmark(preset.benchmark);
                setBaseCurrency(preset.currency);
              }}
              type="button"
            >
              {t(preset.key)}
            </button>
          ))}
        </div>
        <form onSubmit={submit}>
          <div className="optimizer-form">
            <div className="field"><label htmlFor="tickers">{t("portfolio.tickers")}</label><input id="tickers" onChange={(event) => setTickers(event.target.value)} value={tickers} /></div>
            <div className="field"><label htmlFor="cash">{t("portfolio.cashReserve")}</label><input id="cash" min="0" max="95" onChange={(event) => setCashWeight(event.target.value)} type="number" value={cashWeight} /></div>
            <div className="field"><label htmlFor="max-weight">{t("portfolio.maxAsset")}</label><input id="max-weight" min="1" max="100" onChange={(event) => setMaxWeight(event.target.value)} type="number" value={maxWeight} /></div>
            <div className="field"><label htmlFor="initial">{t("portfolio.initialValue", { currency: baseCurrency })}</label><input id="initial" min="100" onChange={(event) => setInitialValue(event.target.value)} type="number" value={initialValue} /></div>
            <button className="primary-button" disabled={loading} type="submit">{loading ? t("portfolio.computing") : t("portfolio.run")}</button>
          </div>
          <div className="advanced-config">
            <span className="toolbar-label">{t("portfolio.backtestSettings")}</span>
            <div className="field"><label htmlFor="lookback">{t("portfolio.lookback")}</label><input id="lookback" min="126" max="1260" onChange={(event) => setLookbackDays(event.target.value)} type="number" value={lookbackDays} /></div>
            <div className="field"><label htmlFor="rebalance">{t("portfolio.rebalance")}</label><input id="rebalance" min="21" max="252" onChange={(event) => setRebalanceDays(event.target.value)} type="number" value={rebalanceDays} /></div>
            <div className="field"><label htmlFor="risk-window">{t("portfolio.riskWindow")}</label><input id="risk-window" min="21" max="252" onChange={(event) => setRiskWindowDays(event.target.value)} type="number" value={riskWindowDays} /></div>
            <div className="field"><label htmlFor="costs">{t("portfolio.costs")}</label><input id="costs" min="0" max="500" step="0.1" onChange={(event) => setTransactionCostBps(event.target.value)} type="number" value={transactionCostBps} /></div>
            <div className="field">
              <label htmlFor="benchmark">{t("portfolio.benchmark")}</label>
              <input id="benchmark" list="benchmark-options" onChange={(event) => setBenchmark(event.target.value.toUpperCase())} value={benchmark} />
              <datalist id="benchmark-options">
                <option value="AUTO">{t("portfolio.benchmarkAuto")}</option>
                <option value="SPY">US / S&amp;P 500</option>
                <option value="000001.SS">China A / SSE Composite</option>
                <option value="^HSI">Hong Kong / Hang Seng</option>
                <option value="ACWI">Global / MSCI ACWI ETF</option>
              </datalist>
            </div>
            <div className="field">
              <label htmlFor="base-currency">{t("portfolio.baseCurrency")}</label>
              <select id="base-currency" onChange={(event) => setBaseCurrency(event.target.value as "USD" | "CNY" | "HKD")} value={baseCurrency}>
                <option value="USD">USD</option>
                <option value="CNY">CNY</option>
                <option value="HKD">HKD</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="covariance-estimator">{t("portfolio.covarianceEstimator")}</label>
              <select
                id="covariance-estimator"
                onChange={(event) => setCovarianceEstimator(event.target.value as "sample" | "oas")}
                value={covarianceEstimator}
              >
                <option value="oas">{t("portfolio.oasEstimator")}</option>
                <option value="sample">{t("portfolio.sampleEstimator")}</option>
              </select>
            </div>
          </div>
        </form>
        <ResearchNotice>{t("portfolio.symbolNotice")}</ResearchNotice>
      </Panel>
      {error ? <ErrorBanner message={error} /> : null}
      {loading ? <LoadingState label={t("portfolio.solving")} /> : null}
      {!loading && !data ? <div className="empty-state"><div><strong>{t("portfolio.emptyTitle")}</strong><p>{t("portfolio.emptyText")}</p></div></div> : null}
      {!loading && data ? (
        <>
          <ResearchNotice>
            {t("portfolio.currencyNotice", {
              currencies: resolvedQuoteCurrencies.join(" / "),
              base: resolvedBaseCurrency,
            })}
          </ResearchNotice>
          <div className="research-toolbar compact-toolbar">
            <div>
              <span className="toolbar-label">{t("portfolio.tools")}</span>
              <p className="toolbar-copy">{actionMessage ? t(actionMessage) : t("portfolio.shareHint")}</p>
            </div>
            <div className="utility-actions">
              <button className="secondary-button" onClick={copyScenarioLink} type="button">{t("common.copyLink")}</button>
              <button className="secondary-button" onClick={exportAllocation} type="button">{t("portfolio.exportAllocation")}</button>
              <button className="secondary-button" onClick={exportBacktest} type="button">{t("portfolio.exportBacktest")}</button>
              <button className="secondary-button" onClick={exportResult} type="button">{t("portfolio.exportResult")}</button>
            </div>
          </div>
          <div className="metrics-grid">
            <MetricCard label={t("portfolio.expectedReturn")} value={percent(data.summary.expected_return)} detail={t("portfolio.returnDetail")} tone="positive" />
            <MetricCard label={t("portfolio.volatility")} value={percent(data.summary.volatility)} detail={t("portfolio.volatilityDetail")} tone="accent" />
            <MetricCard label={t("portfolio.sharpe")} value={data.summary.sharpe_ratio?.toFixed(3) ?? "N/A"} detail={t("portfolio.sharpeDetail")} tone="accent" />
            <MetricCard label={t("portfolio.lossProbability")} value={percent(data.simulation.probability_of_loss)} detail={t("portfolio.pathsDetail", { count: data.simulation.simulations.toLocaleString(numberLocale), seed: data.simulation.seed })} tone="negative" />
          </div>

          <Panel
            title={t("portfolio.estimatorComparisonTitle")}
            eyebrow={t("portfolio.estimatorComparisonEyebrow")}
          >
            <p className="robustness-copy">{t("portfolio.estimatorComparisonDescription")}</p>
            <div className="metrics-grid nested-metrics">
              <MetricCard
                label={t("portfolio.selectedEstimator")}
                value={t(data.covariance_estimator === "oas" ? "portfolio.oasShort" : "portfolio.sampleShort")}
                detail={t("portfolio.selectedEstimatorDetail")}
                tone="accent"
              />
              <MetricCard
                label={t("portfolio.shrinkageIntensity")}
                value={data.estimation_diagnostics.shrinkage_intensity === null ? "N/A" : percent(data.estimation_diagnostics.shrinkage_intensity)}
                detail={t("portfolio.shrinkageDetail")}
                tone="neutral"
              />
              <MetricCard
                label={t("portfolio.conditionNumber")}
                value={diagnosticNumber(data.estimation_diagnostics.covariance_condition_number)}
                detail={t("portfolio.conditionNumberDetail", { value: diagnosticNumber(data.estimation_diagnostics.sample_covariance_condition_number) })}
                tone={data.estimation_diagnostics.covariance_condition_number < data.estimation_diagnostics.sample_covariance_condition_number ? "positive" : "neutral"}
              />
              <MetricCard
                label={t("portfolio.returnObservations")}
                value={data.return_observations.toLocaleString(numberLocale)}
                detail={`${data.price_start} / ${data.price_end}`}
                tone="neutral"
              />
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr>
                  <th>{t("portfolio.estimatorMethod")}</th>
                  <th>{t("portfolio.shrinkageIntensity")}</th>
                  <th>{t("portfolio.conditionNumber")}</th>
                  <th>{t("portfolio.inSampleSharpe")}</th>
                  <th>{t("portfolio.oosCagr")}</th>
                  <th>{t("portfolio.oosSharpe")}</th>
                  <th>{t("portfolio.oosDrawdown")}</th>
                  <th>{t("portfolio.averageTurnover")}</th>
                </tr></thead>
                <tbody>{data.estimator_comparison.map((method) => (
                  <tr key={method.covariance_estimator}>
                    <td>
                      <strong>{t(method.covariance_estimator === "oas" ? "portfolio.oasShort" : "portfolio.sampleShort")}</strong>
                      {method.covariance_estimator === data.covariance_estimator ? ` · ${t("portfolio.selected")}` : ""}
                    </td>
                    <td>{method.shrinkage_intensity === null ? "—" : percent(method.shrinkage_intensity)}</td>
                    <td>{diagnosticNumber(method.covariance_condition_number)}</td>
                    <td>{method.sharpe_ratio?.toFixed(3) ?? "N/A"}</td>
                    <td>{percent(method.backtest_cagr)}</td>
                    <td>{method.backtest_sharpe_ratio?.toFixed(3) ?? "N/A"}</td>
                    <td>{percent(method.backtest_maximum_drawdown)}</td>
                    <td>{percent(method.average_turnover)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <ResearchNotice>{t("portfolio.estimatorComparisonNotice")}</ResearchNotice>
          </Panel>

          <Panel
            title={t("portfolio.strategyComparisonTitle")}
            eyebrow={t("portfolio.strategyComparisonEyebrow")}
          >
            <p className="robustness-copy">{t("portfolio.strategyComparisonDescription")}</p>
            <div className="three-column">
              {data.strategy_comparison.map((strategy) => (
                <MetricCard
                  key={strategy.allocation_strategy}
                  label={t(
                    strategy.allocation_strategy === "max_sharpe"
                      ? "portfolio.maxSharpeStrategy"
                      : strategy.allocation_strategy === "equal_weight"
                        ? "portfolio.equalWeightStrategy"
                        : "portfolio.riskParityStrategy",
                  )}
                  value={percent(strategy.cagr)}
                  detail={`${t("portfolio.sharpe")}: ${strategy.sharpe_ratio?.toFixed(3) ?? "N/A"} · ${t("portfolio.backtestDrawdown")}: ${percent(strategy.maximum_drawdown)}`}
                  tone={strategy.allocation_strategy === "max_sharpe" ? "accent" : "neutral"}
                />
              ))}
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr>
                  <th>{t("portfolio.strategyMethod")}</th>
                  <th>{t("portfolio.covarianceEstimator")}</th>
                  <th>{t("portfolio.cagr")}</th>
                  <th>{t("portfolio.volatility")}</th>
                  <th>{t("portfolio.sharpe")}</th>
                  <th>{t("portfolio.backtestDrawdown")}</th>
                  <th>{t("portfolio.averageTurnover")}</th>
                  <th>{t("portfolio.tradingCosts")}</th>
                </tr></thead>
                <tbody>{data.strategy_comparison.map((strategy) => (
                  <tr key={strategy.allocation_strategy}>
                    <td><strong>{t(
                      strategy.allocation_strategy === "max_sharpe"
                        ? "portfolio.maxSharpeStrategy"
                        : strategy.allocation_strategy === "equal_weight"
                          ? "portfolio.equalWeightStrategy"
                          : "portfolio.riskParityStrategy",
                    )}</strong></td>
                    <td>{strategy.covariance_estimator === null
                      ? t("portfolio.notApplicable")
                      : t(strategy.covariance_estimator === "oas" ? "portfolio.oasShort" : "portfolio.sampleShort")}</td>
                    <td>{percent(strategy.cagr)}</td>
                    <td>{percent(strategy.annualized_volatility)}</td>
                    <td>{strategy.sharpe_ratio?.toFixed(3) ?? "N/A"}</td>
                    <td>{percent(strategy.maximum_drawdown)}</td>
                    <td>{percent(strategy.average_turnover)}</td>
                    <td>{currency(strategy.total_transaction_cost, numberLocale, resolvedBaseCurrency)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <ResearchNotice>{t("portfolio.strategyComparisonNotice")}</ResearchNotice>
          </Panel>

          <div className="two-column">
            <Panel title={t("portfolio.allocation")} eyebrow={t("portfolio.maxSharpe")}>
              <div className="chart-medium"><PlotlyChart data={allocationChart} layout={{ showlegend: false, margin: { l: 25, r: 25, t: 20, b: 25 } }} /></div>
              <div className="allocation-list">
                {data.allocation.map((item) => <div className="allocation-row" key={item.asset}><span>{item.asset === "Cash" ? t("portfolio.cash") : item.asset}</span><div className="allocation-track"><span style={{ width: `${item.weight * 100}%` }} /></div><strong>{percent(item.weight)}</strong></div>)}
              </div>
            </Panel>
            <Panel title={t("portfolio.frontier")} eyebrow={`${data.price_start} / ${data.price_end}`}>
              <div className="chart-tall"><PlotlyChart data={frontierChart} layout={{ xaxis: { title: { text: t("portfolio.volatilityAxis") }, gridcolor: "rgba(148,163,184,.12)" }, yaxis: { title: { text: t("portfolio.returnAxis") }, gridcolor: "rgba(148,163,184,.12)" }, legend: { orientation: "h", y: 1.12 } }} /></div>
            </Panel>
          </div>

          <Panel title={t("portfolio.simulation")} eyebrow={t("portfolio.simulationEyebrow")}>
            <div className="three-column">
              <MetricCard label={t("portfolio.worst")} value={currency(data.simulation.worst_case, numberLocale, resolvedBaseCurrency)} tone="negative" />
              <MetricCard label={t("portfolio.average")} value={currency(data.simulation.average_case, numberLocale, resolvedBaseCurrency)} tone="accent" />
              <MetricCard label={t("portfolio.best")} value={currency(data.simulation.best_case, numberLocale, resolvedBaseCurrency)} tone="positive" />
            </div>
            <div className="chart-tall"><PlotlyChart data={simulationChart} layout={{ hovermode: "x unified", xaxis: { title: { text: t("portfolio.dayAxis") }, gridcolor: "rgba(148,163,184,.12)" }, yaxis: { title: { text: t("portfolio.valueAxis") }, gridcolor: "rgba(148,163,184,.12)", tickprefix: `${resolvedBaseCurrency} ` }, legend: { orientation: "h", y: 1.12 } }} /></div>
          </Panel>

          {data.backtest ? <Panel
            title={t("portfolio.backtestTitle")}
            eyebrow={t("portfolio.backtestEyebrow", { benchmark: data.backtest.benchmark })}
            action={<span className="panel-meta">{data.backtest.start_date} / {data.backtest.end_date}</span>}
          >
            <div className="metrics-grid nested-metrics">
              <MetricCard label={t("portfolio.strategyCagr")} value={percent(data.backtest.strategy.cagr)} detail={t("portfolio.backtestDetail", { count: data.backtest.rebalances.length, lookback: data.backtest.lookback_days, frequency: data.backtest.rebalance_days, cost: data.backtest.transaction_cost_bps })} tone={data.backtest.strategy.cagr >= 0 ? "positive" : "negative"} />
              <MetricCard label={t("portfolio.benchmarkCagr", { benchmark: data.backtest.benchmark })} value={percent(data.backtest.benchmark_statistics.cagr)} detail={`${data.backtest.benchmark} · ${data.backtest.start_date}`} tone="accent" />
              <MetricCard label={t("portfolio.backtestDrawdown")} value={percent(data.backtest.strategy.maximum_drawdown)} detail={`${t("portfolio.sharpe")}: ${data.backtest.strategy.sharpe_ratio?.toFixed(3) ?? "N/A"}`} tone="negative" />
              <MetricCard label={t("portfolio.tradingCosts")} value={currency(data.backtest.total_transaction_cost, numberLocale, resolvedBaseCurrency)} detail={`${data.backtest.transaction_cost_bps} bps`} tone="neutral" />
            </div>
            <div className="two-column two-equal">
              <Panel title={t("portfolio.backtestPath")} eyebrow={t("portfolio.backtestPathEyebrow")} className="nested-panel">
                <div className="chart-medium"><PlotlyChart data={backtestPathChart} layout={{ hovermode: "x unified", xaxis: { gridcolor: "rgba(148,163,184,.12)" }, yaxis: { gridcolor: "rgba(148,163,184,.12)", tickprefix: `${resolvedBaseCurrency} ` }, legend: { orientation: "h", y: 1.12 } }} /></div>
              </Panel>
              <Panel title={t("portfolio.drawdownTitle")} eyebrow={t("portfolio.drawdownEyebrow")} className="nested-panel">
                <div className="chart-medium"><PlotlyChart data={backtestDrawdownChart} layout={{ hovermode: "x unified", xaxis: { gridcolor: "rgba(148,163,184,.12)" }, yaxis: { gridcolor: "rgba(148,163,184,.12)", ticksuffix: "%" }, legend: { orientation: "h", y: 1.12 } }} /></div>
              </Panel>
            </div>
            {data.backtest.bootstrap_uncertainty ? <Panel
              title={t("portfolio.bootstrapTitle")}
              eyebrow={t("portfolio.bootstrapEyebrow")}
              className="nested-panel"
            >
              <p className="robustness-copy">{t("portfolio.bootstrapDescription", {
                block: data.backtest.bootstrap_uncertainty.block_length_days,
                confidence: Math.round(data.backtest.bootstrap_uncertainty.confidence_level * 100),
                resamples: data.backtest.bootstrap_uncertainty.resamples.toLocaleString(numberLocale),
              })}</p>
              <div className="metrics-grid nested-metrics">
                <MetricCard
                  label={t("portfolio.bootstrapOutperformance", { benchmark: data.backtest.benchmark })}
                  value={percent(data.backtest.bootstrap_uncertainty.strategy_cagr_above_benchmark_fraction)}
                  detail={t("portfolio.bootstrapOutperformanceDetail")}
                  tone="accent"
                />
                <MetricCard
                  label={t("portfolio.returnObservations")}
                  value={data.backtest.bootstrap_uncertainty.observations.toLocaleString(numberLocale)}
                  detail={`${data.backtest.bootstrap_uncertainty.resamples.toLocaleString(numberLocale)} × ${data.backtest.bootstrap_uncertainty.block_length_days}d · seed ${data.backtest.bootstrap_uncertainty.seed}`}
                  tone="neutral"
                />
              </div>
              <div className="table-scroll">
                <table className="data-table bootstrap-table">
                  <thead><tr>
                    <th>{t("portfolio.bootstrapMetric")}</th>
                    <th>{t("portfolio.bootstrapSeries")}</th>
                    <th>{t("portfolio.bootstrapEstimate")}</th>
                    <th>{t("portfolio.bootstrapMedian")}</th>
                    <th>{t("portfolio.bootstrapInterval", { confidence: Math.round(data.backtest.bootstrap_uncertainty.confidence_level * 100) })}</th>
                  </tr></thead>
                  <tbody>{bootstrapMetrics.flatMap((definition) => (
                    (["strategy", "benchmark"] as const).map((series) => {
                      const interval = data.backtest.bootstrap_uncertainty?.[series][definition.key];
                      if (!interval) return null;
                      return <tr key={`${definition.key}-${series}`}>
                        <td><strong>{t(definition.label)}</strong></td>
                        <td>{series === "strategy"
                          ? t("portfolio.bootstrapStrategy")
                          : t("portfolio.bootstrapBenchmark", { benchmark: data.backtest.benchmark })}</td>
                        <td>{bootstrapValue(interval.estimate, definition.format)}</td>
                        <td>{bootstrapValue(interval.median, definition.format)}</td>
                        <td>{bootstrapValue(interval.lower, definition.format)} – {bootstrapValue(interval.upper, definition.format)}</td>
                      </tr>;
                    })
                  ))}</tbody>
                </table>
              </div>
              <ResearchNotice>{t("portfolio.bootstrapNotice")}</ResearchNotice>
            </Panel> : null}
            {data.backtest.risk_diagnostics ? <>
              <div className="panel-heading risk-heading">
                <div>
                  <span className="panel-eyebrow">{t("portfolio.riskDiagnosticsEyebrow")}</span>
                  <h3>{t("portfolio.riskDiagnostics")}</h3>
                </div>
              </div>
              <div className="metrics-grid nested-metrics">
                <MetricCard
                  label={t("portfolio.sortino")}
                  value={data.backtest.risk_diagnostics.sortino_ratio?.toFixed(3) ?? "N/A"}
                  detail={t("portfolio.downsideDeviationDetail", { value: percent(data.backtest.risk_diagnostics.downside_deviation) })}
                  tone="accent"
                />
                <MetricCard
                  label={t("portfolio.beta", { benchmark: data.backtest.benchmark })}
                  value={data.backtest.risk_diagnostics.beta?.toFixed(3) ?? "N/A"}
                  detail={t("portfolio.correlationDetail", { value: data.backtest.risk_diagnostics.correlation?.toFixed(3) ?? "N/A" })}
                  tone="accent"
                />
                <MetricCard
                  label={t("portfolio.trackingError")}
                  value={percent(data.backtest.risk_diagnostics.tracking_error)}
                  detail={t("portfolio.informationRatioDetail", { value: data.backtest.risk_diagnostics.information_ratio?.toFixed(3) ?? "N/A" })}
                  tone="neutral"
                />
                <MetricCard
                  label={t("portfolio.longestDrawdown")}
                  value={t("portfolio.tradingDays", { days: data.backtest.risk_diagnostics.longest_drawdown_days })}
                  detail={t("portfolio.benchmarkDrawdownDuration", { benchmark: data.backtest.benchmark, days: data.backtest.risk_diagnostics.benchmark_longest_drawdown_days })}
                  tone="negative"
                />
              </div>
              <Panel
                title={t("portfolio.rollingRiskTitle")}
                eyebrow={t("portfolio.rollingRiskEyebrow", { window: data.backtest.risk_window_days })}
                className="nested-panel rolling-risk-panel"
              >
                <div className="chart-medium"><PlotlyChart data={rollingRiskChart} layout={{
                  hovermode: "x unified",
                  xaxis: { gridcolor: "rgba(148,163,184,.12)" },
                  yaxis: { title: { text: t("portfolio.volatilityAxis") }, gridcolor: "rgba(148,163,184,.12)", ticksuffix: "%" },
                  yaxis2: { title: { text: "Beta" }, overlaying: "y", side: "right", showgrid: false },
                  legend: { orientation: "h", y: 1.14 },
                }} /></div>
              </Panel>
            </> : null}
            <Panel
              title={t("portfolio.robustnessTitle")}
              eyebrow={t("portfolio.robustnessEyebrow")}
              className="nested-panel robustness-panel"
              action={<div className="utility-actions">
                {robustnessData ? <button className="secondary-button" onClick={exportRobustness} type="button">{t("portfolio.exportRobustness")}</button> : null}
                <button className="secondary-button" disabled={robustnessLoading} onClick={runRobustnessAnalysis} type="button">
                  {robustnessLoading ? t("portfolio.runningRobustness") : t("portfolio.runRobustness")}
                </button>
              </div>}
            >
              <p className="robustness-copy">{t("portfolio.robustnessDescription")}</p>
              {robustnessError ? <ErrorBanner message={robustnessError} /> : null}
              {robustnessData ? <>
                <div className="metrics-grid nested-metrics robustness-metrics">
                  <MetricCard
                    label={t("portfolio.medianCagr")}
                    value={percent(robustnessData.median_cagr)}
                    detail={t("portfolio.cagrDispersionDetail", { value: percent(robustnessData.cagr_dispersion) })}
                    tone="positive"
                  />
                  <MetricCard
                    label={t("portfolio.medianSharpe")}
                    value={robustnessData.median_sharpe_ratio?.toFixed(3) ?? "N/A"}
                    detail={t("portfolio.benchmarkCagrDetail", { benchmark: robustnessData.benchmark, value: percent(robustnessData.benchmark_cagr) })}
                    tone="accent"
                  />
                  <MetricCard
                    label={t("portfolio.worstGridDrawdown")}
                    value={percent(robustnessData.worst_maximum_drawdown)}
                    detail={t("portfolio.scenarios", { count: robustnessData.scenarios.length })}
                    tone="negative"
                  />
                  <MetricCard
                    label={t("portfolio.positiveExcess", { benchmark: robustnessData.benchmark })}
                    value={percent(robustnessData.positive_excess_fraction)}
                    detail={`${robustnessData.start_date} / ${robustnessData.end_date}`}
                    tone="accent"
                  />
                </div>
                <Panel title={t("portfolio.robustnessHeatmap")} eyebrow={t("portfolio.robustnessHeatmapEyebrow")} className="nested-panel robustness-heatmap">
                  <div className="chart-medium"><PlotlyChart data={robustnessHeatmap} layout={{
                    xaxis: { title: { text: t("portfolio.rebalanceAxis") }, type: "category" },
                    yaxis: { title: { text: t("portfolio.lookbackAxis") }, type: "category" },
                    margin: { l: 70, r: 40, t: 25, b: 65 },
                  }} /></div>
                </Panel>
                <div className="robustness-table">
                  <div className="panel-heading compact-heading"><div><h3>{t("portfolio.scenarioGrid")}</h3></div></div>
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead><tr>
                        <th>{t("portfolio.lookbackAxis")}</th>
                        <th>{t("portfolio.rebalanceAxis")}</th>
                        <th>{t("portfolio.cagr")}</th>
                        <th>{t("portfolio.excessCagr")}</th>
                        <th>{t("portfolio.sharpe")}</th>
                        <th>{t("portfolio.backtestDrawdown")}</th>
                        <th>{t("portfolio.averageTurnover")}</th>
                        <th>{t("portfolio.tradingCosts")}</th>
                      </tr></thead>
                      <tbody>{robustnessData.scenarios.map((scenario) => (
                        <tr key={`${scenario.lookback_days}-${scenario.rebalance_days}`}>
                          <td>{scenario.lookback_days}</td>
                          <td>{scenario.rebalance_days}</td>
                          <td>{percent(scenario.cagr)}</td>
                          <td>{percent(scenario.excess_cagr)}</td>
                          <td>{scenario.sharpe_ratio?.toFixed(3) ?? "N/A"}</td>
                          <td>{percent(scenario.maximum_drawdown)}</td>
                          <td>{percent(scenario.average_turnover)}</td>
                          <td>{currency(scenario.total_transaction_cost, numberLocale, resolvedRobustnessCurrency)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                </div>
                <ResearchNotice>{t("portfolio.robustnessNotice")}</ResearchNotice>
              </> : null}
            </Panel>
            <div className="rebalance-log">
              <div className="panel-heading compact-heading">
                <div><span className="panel-eyebrow">{t("portfolio.rebalanceLogEyebrow")}</span><h3>{t("portfolio.rebalanceLog")}</h3></div>
              </div>
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>{t("portfolio.rebalanceDate")}</th><th>{t("portfolio.turnover")}</th><th>{t("portfolio.cost")}</th><th>{t("portfolio.targetWeights")}</th></tr></thead>
                  <tbody>
                    {data.backtest.rebalances.slice(-5).reverse().map((event) => (
                      <tr key={event.date}>
                        <td>{event.date}</td>
                        <td>{percent(event.turnover)}</td>
                        <td>{currency(event.transaction_cost, numberLocale, resolvedBaseCurrency)}</td>
                        <td>{Object.entries(event.weights).filter(([, weight]) => weight > 0.0005).map(([asset, weight]) => `${asset} ${percent(weight)}`).join(" · ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <ResearchNotice>{t("portfolio.backtestNotice")}</ResearchNotice>
          </Panel> : null}

          <div className="two-column two-equal">
            <Panel title={t("portfolio.minVol")} eyebrow={t("portfolio.alternative")}>
              <div className="definition-grid">
                <div className="definition-item"><span>{t("portfolio.expectedReturn")}</span><strong>{percent(data.minimum_volatility.expected_return)}</strong></div>
                <div className="definition-item"><span>{t("portfolio.volatility")}</span><strong>{percent(data.minimum_volatility.volatility)}</strong></div>
                <div className="definition-item"><span>{t("portfolio.sharpe")}</span><strong>{data.minimum_volatility.sharpe_ratio?.toFixed(3) ?? "N/A"}</strong></div>
              </div>
            </Panel>
            <Panel title={t("portfolio.assumptions")} eyebrow={t("portfolio.readBefore")}>
              <ul className="assumption-list">{assumptionKeys.map((key) => <li key={key}>{t(key)}</li>)}</ul>
            </Panel>
          </div>
          <ResearchNotice>{t("portfolio.disclaimer")}</ResearchNotice>
        </>
      ) : null}
    </>
  );
}
