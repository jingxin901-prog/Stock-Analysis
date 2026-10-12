"use client";

import type { CSSProperties, FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { PageHeader } from "@/components/page-header";
import {
  FactorContributionChart,
  ValuationDistributionChart,
} from "@/components/factor-diagnostics";
import { PriceChart } from "@/components/price-chart";
import {
  ErrorBanner,
  LoadingState,
  MetricCard,
  Panel,
  ResearchNotice,
} from "@/components/ui";
import {
  getApiErrorMessage,
  getStockAnalysis,
  getStockExplanation,
  searchInstruments,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { copyText, downloadCsv, downloadJson, replaceQuery } from "@/lib/research-tools";
import type {
  InstrumentContext,
  InstrumentSearchResult,
  StockAnalysisResponse,
  StockExplanationResponse,
} from "@/types/api";

const DEFAULT_WATCHLIST = ["AAPL", "NVDA", "600519.SS", "000858.SZ", "0700.HK"];
const WATCHLIST_STORAGE_KEY = "quantai-watchlist-v1";

type InputMarket = "auto" | "shanghai" | "shenzhen" | "hong-kong" | "us";
type PeerMode = "auto" | "custom";

const MARKET_LABEL_KEYS = {
  us: "stock.marketUs",
  china_a: "stock.marketChinaA",
  hong_kong: "stock.marketHongKongLabel",
  united_kingdom: "stock.marketUnitedKingdom",
  canada: "stock.marketCanada",
  japan: "stock.marketJapan",
  australia: "stock.marketAustralia",
  germany: "stock.marketGermany",
  france: "stock.marketFrance",
} as const;

const PEER_METHOD_KEYS = {
  sector_market_cap: "stock.peerMethodSectorCap",
  sector: "stock.peerMethodSector",
  market_cap: "stock.peerMethodMarketCap",
  market_fallback: "stock.peerMethodMarket",
  global_fallback: "stock.peerMethodGlobal",
  custom: "stock.peerMethodCustom",
} as const;

const CAP_BAND_KEYS = {
  mega: "stock.capMega",
  large: "stock.capLarge",
  mid: "stock.capMid",
  small: "stock.capSmall",
  micro: "stock.capMicro",
} as const;

const SECTOR_LABEL_KEYS = {
  technology: "stock.sectorTechnology",
  communication_services: "stock.sectorCommunication",
  consumer_cyclical: "stock.sectorConsumerCyclical",
  consumer_defensive: "stock.sectorConsumerDefensive",
  financials: "stock.sectorFinancials",
  industrials: "stock.sectorIndustrials",
  healthcare: "stock.sectorHealthcare",
  energy: "stock.sectorEnergy",
  materials: "stock.sectorMaterials",
  real_estate: "stock.sectorRealEstate",
  utilities: "stock.sectorUtilities",
} as const;

function normalizedSector(value: string | null | undefined) {
  if (!value) return undefined;
  const normalized = value.trim().toLowerCase().replaceAll(" ", "_");
  if (normalized === "financial_services") return "financials";
  if (normalized === "basic_materials") return "materials";
  if (normalized === "consumer_discretionary") return "consumer_cyclical";
  if (normalized === "consumer_staples") return "consumer_defensive";
  return normalized;
}

function formatMarketTicker(value: string, market: InputMarket) {
  const symbol = value.trim().toUpperCase();
  if (!symbol || /[.^=-]/.test(symbol)) return symbol;
  if (market === "shanghai" && /^\d{6}$/.test(symbol)) return `${symbol}.SS`;
  if (market === "shenzhen" && /^\d{6}$/.test(symbol)) return `${symbol}.SZ`;
  if (market === "hong-kong" && /^\d{1,5}$/.test(symbol)) {
    return `${symbol.padStart(4, "0")}.HK`;
  }
  return symbol;
}

function inferInstrumentContext(ticker: string): InstrumentContext {
  const symbol = ticker.toUpperCase();
  if (symbol.endsWith(".SS") || symbol.endsWith(".SZ")) {
    return { market: "china_a", currency: "CNY", suggested_benchmark: "000001.SS" };
  }
  if (symbol.endsWith(".HK")) {
    return { market: "hong_kong", currency: "HKD", suggested_benchmark: "^HSI" };
  }
  return { market: "us", currency: "USD", suggested_benchmark: "SPY" };
}

type StockActionMessage =
  | { key: "stock.saved" | "stock.removed"; ticker: string }
  | { key: "common.linkCopied" | "stock.exported" };

function percent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function number(value: number | null, digits = 2) {
  return value === null ? "N/A" : value.toFixed(digits);
}

function compactMarketCap(
  value: number | null | undefined,
  currency: string,
  locale: string,
) {
  if (value === null || value === undefined) return "N/A";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function localDateTime(value: string | null | undefined, locale: string) {
  if (!value) return "N/A";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(locale);
}

function peerInputTokens(value: string) {
  return value
    .split(/[\s,|]+/)
    .map((ticker) => ticker.trim().toUpperCase())
    .filter(Boolean);
}

function parsePeerInput(value: string, target: string) {
  return peerInputTokens(value)
    .filter(
      (ticker, index, values) =>
        ticker !== target
        && /^[A-Z0-9.^=-]{1,20}$/.test(ticker)
        && values.indexOf(ticker) === index,
    );
}

function hasValidPeerInput(value: string, target: string) {
  const tokens = peerInputTokens(value).filter((ticker) => ticker !== target);
  return tokens.every((ticker) => /^[A-Z0-9.^=-]{1,20}$/.test(ticker))
    && new Set(tokens).size === tokens.length;
}

export default function StockAnalysisPage() {
  const [query, setQuery] = useState("NVDA");
  const [inputMarket, setInputMarket] = useState<InputMarket>("auto");
  const [peerMode, setPeerMode] = useState<PeerMode>("auto");
  const [customPeerInput, setCustomPeerInput] = useState("");
  const [activePeerRequest, setActivePeerRequest] = useState<string[]>([]);
  const [data, setData] = useState<StockAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<StockExplanationResponse | null>(null);
  const [explanationLoading, setExplanationLoading] = useState(true);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>(DEFAULT_WATCHLIST);
  const [actionMessage, setActionMessage] = useState<StockActionMessage | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchStatus, setSearchStatus] = useState<"idle" | "loading" | "ready">("idle");
  const [searchResults, setSearchResults] = useState<InstrumentSearchResult[]>([]);
  const [searchFallback, setSearchFallback] = useState(false);
  const { apiLocale, locale, t } = useI18n();
  const translationRef = useRef(t);
  const numberLocale = locale === "zh" ? "zh-CN" : "en-US";
  const activeTicker = data?.ticker;

  useEffect(() => {
    translationRef.current = t;
  }, [t]);

  function runAnalysis(ticker: string) {
    const peers = peerMode === "custom" ? parsePeerInput(customPeerInput, ticker) : [];
    if (
      peerMode === "custom"
      && (!hasValidPeerInput(customPeerInput, ticker) || peers.length < 2 || peers.length > 9)
    ) {
      setError(t("stock.peerValidation"));
      return;
    }
    setQuery(ticker);
    setSearchOpen(false);
    setSearchStatus("idle");
    setLoading(true);
    setError(null);
    setExplanation(null);
    setExplanationError(null);
    setExplanationLoading(true);
    const params = new URLSearchParams(window.location.search);
    params.set("ticker", ticker);
    if (peers.length) params.set("peers", peers.join("|"));
    else params.delete("peers");
    replaceQuery(params);
    getStockAnalysis(ticker, peers)
      .then((response) => {
        setActivePeerRequest(peers);
        setData(response);
      })
      .catch((reason: unknown) => {
        setError(getApiErrorMessage(reason, t));
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let active = true;
    const initialParams = new URLSearchParams(window.location.search);
    const requestedTicker = initialParams
      .get("ticker")
      ?.trim()
      .toUpperCase();
    const initialTicker = requestedTicker && /^[A-Z0-9.^=-]{1,20}$/.test(requestedTicker)
      ? requestedTicker
      : "NVDA";
    const requestedPeers = initialParams.get("peers") ?? "";
    const initialPeers = parsePeerInput(requestedPeers, initialTicker);
    const useCustomPeers = initialPeers.length >= 2 && initialPeers.length <= 9;
    const params = new URLSearchParams(initialParams);
    params.set("ticker", initialTicker);
    if (useCustomPeers) params.set("peers", initialPeers.join("|"));
    else params.delete("peers");
    replaceQuery(params);
    const frame = window.requestAnimationFrame(() => {
      setQuery(initialTicker);
      setPeerMode(useCustomPeers ? "custom" : "auto");
      setCustomPeerInput(useCustomPeers ? initialPeers.join(", ") : "");
    });
    getStockAnalysis(initialTicker, useCustomPeers ? initialPeers : [])
      .then((response) => {
        if (active) {
          setActivePeerRequest(useCustomPeers ? initialPeers : []);
          setData(response);
          setLoading(false);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(getApiErrorMessage(reason, translationRef.current));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      window.cancelAnimationFrame(frame);
    };
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem(WATCHLIST_STORAGE_KEY);
    if (!stored) return;
    try {
      const parsed = JSON.parse(stored) as unknown;
      if (Array.isArray(parsed)) {
        const tickers = parsed
          .filter((item): item is string => typeof item === "string")
          .map((item) => item.trim().toUpperCase())
          .filter((item, index, items) => item && items.indexOf(item) === index)
          .slice(0, 12);
        if (tickers.length) {
          const frame = window.requestAnimationFrame(() => setWatchlist(tickers));
          return () => window.cancelAnimationFrame(frame);
        }
      }
    } catch {
      window.localStorage.removeItem(WATCHLIST_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (!activeTicker) return;
    let active = true;
    getStockExplanation(activeTicker, apiLocale, activePeerRequest)
      .then((response) => {
        if (active) {
          setExplanation(response);
          setExplanationError(null);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setExplanationError(getApiErrorMessage(reason, t));
        }
      })
      .finally(() => {
        if (active) setExplanationLoading(false);
      });
    return () => {
      active = false;
    };
  }, [activeTicker, activePeerRequest, apiLocale, t]);

  useEffect(() => {
    const searchQuery = query.trim();
    if (!searchOpen || searchQuery.length < 2) {
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      setSearchStatus("loading");
      searchInstruments(searchQuery)
        .then((response) => {
          if (!active) return;
          setSearchResults(response.results);
          setSearchFallback(Boolean(response.warning));
          setSearchStatus("ready");
        })
        .catch(() => {
          if (!active) return;
          setSearchResults([]);
          setSearchFallback(true);
          setSearchStatus("ready");
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query, searchOpen]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const searchMatch = inputMarket === "auto" ? searchResults[0]?.symbol : undefined;
    const ticker = searchMatch ?? formatMarketTicker(query, inputMarket);
    if (!/^[A-Z0-9.^=-]{1,20}$/.test(ticker)) {
      setError(t("stock.searchSelect"));
      return;
    }
    runAnalysis(ticker);
  }

  function selectTicker(ticker: string) {
    if (!loading && ticker !== activeTicker) runAnalysis(ticker);
  }

  function selectSearchResult(result: InstrumentSearchResult) {
    setInputMarket("auto");
    runAnalysis(result.symbol);
  }

  function toggleWatchlist() {
    if (!activeTicker) return;
    const isSaved = watchlist.includes(activeTicker);
    const next = isSaved
      ? watchlist.filter((ticker) => ticker !== activeTicker)
      : [...watchlist, activeTicker].slice(-12);
    setWatchlist(next);
    window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(next));
    setActionMessage({ key: isSaved ? "stock.removed" : "stock.saved", ticker: activeTicker });
  }

  async function copyResearchLink() {
    if (!activeTicker) return;
    const params = new URLSearchParams(window.location.search);
    params.set("ticker", activeTicker);
    await copyText(replaceQuery(params));
    setActionMessage({ key: "common.linkCopied" });
  }

  function exportSummary() {
    if (!data) return;
    downloadJson(`quantai-${data.ticker.toLowerCase()}-research-${data.risk.end_date}.json`, {
      exported_at_utc: new Date().toISOString(),
      methodology: "QuantAI historical research snapshot",
      ticker: data.ticker,
      source: data.source,
      risk: data.risk,
      fundamentals: data.fundamentals,
      factor_score: data.factor_score,
      instrument: data.instrument ?? inferInstrumentContext(data.ticker),
      ml_experiment: data.ml_experiment,
      explanation,
      disclaimer: data.disclaimer,
    });
    setActionMessage({ key: "stock.exported" });
  }

  function exportPrices() {
    if (!data) return;
    downloadCsv(
      `quantai-${data.ticker.toLowerCase()}-prices-${data.risk.end_date}.csv`,
      ["date", "open", "high", "low", "close", "adjusted_close", "volume"],
      data.prices.map((point) => [
        point.date,
        point.open,
        point.high,
        point.low,
        point.close,
        point.adjusted_close,
        point.volume,
      ]),
    );
    setActionMessage({ key: "stock.exported" });
  }

  function exportFactorTable() {
    if (!data?.factor_score.peer_rankings?.length) return;
    downloadCsv(
      `quantai-${data.ticker.toLowerCase()}-factor-ranking-${data.risk.end_date}.csv`,
      [
        "rank", "ticker", "quant_score", "value_score", "momentum_score",
        "quality_score", "data_coverage", "value_coverage", "momentum_coverage",
        "quality_coverage", "pe_ratio", "pb_ratio", "ev_to_ebitda",
        "momentum_3m", "momentum_6m", "momentum_12m", "roe",
        "profit_margin", "debt_ratio",
      ],
      data.factor_score.peer_rankings.map((row) => [
        row.rank, row.ticker, row.quant_score, row.value_score, row.momentum_score,
        row.quality_score, row.data_coverage, row.value_coverage,
        row.momentum_coverage, row.quality_coverage, row.pe_ratio, row.pb_ratio,
        row.ev_to_ebitda, row.momentum_3m, row.momentum_6m, row.momentum_12m,
        row.roe, row.profit_margin, row.debt_ratio,
      ]),
    );
    setActionMessage({ key: "stock.exported" });
  }

  const riskTone = data && data.risk.annualized_volatility > 0.45 ? "negative" : "accent";
  const instrument = data?.instrument ?? inferInstrumentContext(data?.ticker ?? query);
  const marketLabelKey = instrument
    ? MARKET_LABEL_KEYS[instrument.market as keyof typeof MARKET_LABEL_KEYS]
      ?? "stock.marketGlobal"
    : "stock.marketGlobal";
  const factorMarketMatched = data
    ? data.factor_score.market_matched ?? data.factor_score.universe.every(
      (ticker) => inferInstrumentContext(ticker).market === instrument.market,
    )
    : true;
  const factorUniverseMarket = data?.factor_score.universe_market
    ?? (factorMarketMatched ? instrument.market : "global");
  const factorUniverseLabelKey = MARKET_LABEL_KEYS[
    factorUniverseMarket as keyof typeof MARKET_LABEL_KEYS
  ] ?? "stock.marketGlobal";
  const factorUniverseLabel = data?.factor_score.peer_selection_method === "custom"
    ? t("stock.customUniverse")
    : t(factorUniverseLabelKey);
  const peerMethod = data?.factor_score.peer_selection_method ?? "market_fallback";
  const peerMethodKey = PEER_METHOD_KEYS[
    peerMethod as keyof typeof PEER_METHOD_KEYS
  ] ?? "stock.peerMethodMarket";
  const peerCapBand = data?.factor_score.peer_market_cap_band;
  const peerCapKey = peerCapBand
    ? CAP_BAND_KEYS[peerCapBand as keyof typeof CAP_BAND_KEYS]
    : undefined;
  const sectorCode = normalizedSector(
    data?.factor_score.peer_sector ?? data?.fundamentals.sector,
  );
  const sectorLabelKey = sectorCode
    ? SECTOR_LABEL_KEYS[sectorCode as keyof typeof SECTOR_LABEL_KEYS]
    : undefined;
  const sectorLabel = sectorLabelKey
    ? t(sectorLabelKey)
    : data?.fundamentals.sector ?? t("stock.peerUnknown");
  const inputHint = {
    auto: t("stock.symbolHintAuto"),
    shanghai: t("stock.symbolHintShanghai"),
    shenzhen: t("stock.symbolHintShenzhen"),
    "hong-kong": t("stock.symbolHintHongKong"),
    us: t("stock.symbolHintUS"),
  }[inputMarket];

  return (
    <>
      <PageHeader
        eyebrow={t("stock.eyebrow")}
        title={t("stock.title")}
        description={t("stock.description")}
      />
      <div className="topline">
        <span>{t("stock.window")}</span>
        <form className="search-form" onSubmit={submit}>
          <label className="sr-only" htmlFor="stock-market">{t("stock.marketSelector")}</label>
          <select
            id="stock-market"
            onChange={(event) => setInputMarket(event.target.value as InputMarket)}
            value={inputMarket}
          >
            <option value="auto">{t("stock.marketAuto")}</option>
            <option value="shanghai">{t("stock.marketShanghai")}</option>
            <option value="shenzhen">{t("stock.marketShenzhen")}</option>
            <option value="hong-kong">{t("stock.marketHongKong")}</option>
            <option value="us">{t("stock.marketUS")}</option>
          </select>
          <div className="instrument-search">
            <input
              aria-label={t("stock.searchLabel")}
              autoComplete="off"
              maxLength={64}
              onChange={(event) => {
                setQuery(event.target.value);
                setSearchOpen(true);
                setSearchStatus("idle");
                setSearchResults([]);
                setSearchFallback(false);
              }}
              onFocus={() => {
                setSearchOpen(true);
                setSearchStatus("idle");
              }}
              placeholder={t("stock.searchPlaceholder")}
              value={query}
            />
            {searchOpen && searchStatus !== "idle" ? (
              <div className="instrument-search-menu" role="listbox">
                {searchStatus === "loading" ? (
                  <div className="instrument-search-status">{t("stock.searching")}</div>
                ) : searchResults.length ? (
                  searchResults.map((result) => (
                    <button
                      className="instrument-search-result"
                      aria-selected="false"
                      key={result.symbol}
                      onClick={() => selectSearchResult(result)}
                      onMouseDown={(event) => event.preventDefault()}
                      role="option"
                      type="button"
                    >
                      <span>
                        <strong>{result.symbol}</strong>
                        <small>{result.name}</small>
                      </span>
                      <em>{result.exchange} · {result.currency}</em>
                    </button>
                  ))
                ) : (
                  <div className="instrument-search-status">{t("stock.searchEmpty")}</div>
                )}
                {searchStatus === "ready" && searchFallback ? (
                  <div className="instrument-search-note">{t("stock.searchFallback")}</div>
                ) : null}
              </div>
            ) : null}
          </div>
          <button className="primary-button" disabled={loading} type="submit">{t("stock.analyze")}</button>
        </form>
      </div>
      <p className="symbol-hint">{inputHint}</p>
      <div className="peer-config">
        <label className="field">
          <span>{t("stock.peerMode")}</span>
          <select
            disabled={loading}
            onChange={(event) => setPeerMode(event.target.value as PeerMode)}
            value={peerMode}
          >
            <option value="auto">{t("stock.peerAuto")}</option>
            <option value="custom">{t("stock.peerCustom")}</option>
          </select>
        </label>
        {peerMode === "custom" ? (
          <label className="field peer-input-field">
            <span>{t("stock.peerInput")}</span>
            <input
              disabled={loading}
              onChange={(event) => setCustomPeerInput(event.target.value)}
              placeholder={t("stock.peerPlaceholder")}
              value={customPeerInput}
            />
          </label>
        ) : null}
        <p>{peerMode === "custom" ? t("stock.peerHintCustom") : t("stock.peerHintAuto")}</p>
      </div>
      <div className="research-toolbar">
        <div className="watchlist-block">
          <span className="toolbar-label">{t("stock.watchlist")}</span>
          <div className="ticker-chips">
            {watchlist.map((ticker) => (
              <button
                className={ticker === activeTicker ? "ticker-chip ticker-chip-active" : "ticker-chip"}
                disabled={loading}
                key={ticker}
                onClick={() => selectTicker(ticker)}
                type="button"
              >
                {ticker}
              </button>
            ))}
          </div>
        </div>
        <div className="utility-actions">
          <button className="secondary-button" disabled={!data} onClick={toggleWatchlist} type="button">
            {activeTicker && watchlist.includes(activeTicker) ? t("stock.removeWatchlist") : t("stock.addWatchlist")}
          </button>
          <button className="secondary-button" disabled={!data} onClick={copyResearchLink} type="button">{t("common.copyLink")}</button>
          <button className="secondary-button" disabled={!data} onClick={exportSummary} type="button">{t("common.exportJson")}</button>
          <button className="secondary-button" disabled={!data} onClick={exportPrices} type="button">{t("stock.exportPrices")}</button>
        </div>
      </div>
      <div className="toolbar-feedback" aria-live="polite">
        {actionMessage
          ? t(actionMessage.key, "ticker" in actionMessage ? { ticker: actionMessage.ticker } : undefined)
          : t("stock.shareHint")}
      </div>
      {error ? <ErrorBanner message={error} /> : null}
      {loading ? <LoadingState label={t("stock.loading", { ticker: query.toUpperCase() })} /> : null}
      {!loading && data ? (
        <>
          <div className="instrument-context" aria-label={t("stock.marketContext")}>
            <div><span>{t("stock.companyContext")}</span><strong>{data.fundamentals.company_name ?? data.ticker}</strong></div>
            <div><span>{t("stock.marketContext")}</span><strong>{t(marketLabelKey)}</strong></div>
            <div><span>{t("stock.currencyContext")}</span><strong>{instrument.currency}</strong></div>
            <div><span>{t("stock.benchmarkContext")}</span><strong>{instrument.suggested_benchmark}</strong></div>
            <div><span>{t("stock.sectorContext")}</span><strong>{sectorLabel}</strong></div>
            <div><span>{t("stock.marketCapContext")}</span><strong>{compactMarketCap(data.fundamentals.market_cap, instrument.currency, numberLocale)}</strong></div>
          </div>
          {data.data_status?.served_from_cache ? (
            <ResearchNotice>
              {t("stock.cachedDataNotice", {
                cachedAt: localDateTime(data.data_status.cached_at_utc, numberLocale),
                asOf: data.data_status.last_observation,
              })}
            </ResearchNotice>
          ) : null}
          {data.fundamentals.source === "fundamental-cache" ? (
            <ResearchNotice>{t("stock.cachedFundamentalsNotice")}</ResearchNotice>
          ) : null}
          {data.fundamentals.source === "unavailable" ? (
            <ResearchNotice>{t("stock.unavailableFundamentalsNotice")}</ResearchNotice>
          ) : null}
          <div className="metrics-grid">
            <MetricCard label={t("stock.annualReturn")} value={percent(data.risk.annualized_return)} detail={`${data.risk.start_date} — ${data.risk.end_date}`} tone={data.risk.annualized_return >= 0 ? "positive" : "negative"} />
            <MetricCard label={t("stock.annualVolatility")} value={percent(data.risk.annualized_volatility)} detail={t("stock.annualization")} tone={riskTone} />
            <MetricCard label={t("stock.sharpe")} value={number(data.risk.sharpe_ratio, 3)} detail={t("stock.riskFree")} tone="accent" />
            <MetricCard label={t("stock.drawdown")} value={percent(data.risk.maximum_drawdown)} detail={t("stock.drawdownDetail")} tone="negative" />
          </div>

          <Panel
            title={t("stock.aiTitle")}
            eyebrow={t("stock.aiEyebrow")}
            action={
              explanation ? (
                <span className="tag">
                  {explanation.source === "openai" ? explanation.model : t("stock.deterministic")}
                </span>
              ) : null
            }
          >
            {explanationLoading ? (
              <div className="ai-loading">{t("stock.interpreting")}</div>
            ) : null}
            {explanationError ? <ErrorBanner message={explanationError} /> : null}
            {explanation ? (
              <>
                <div className="ai-summary">
                  <span className={`risk-badge risk-${explanation.risk_level.toLowerCase()}`}>
                    {{ Lower: t("stock.risk.Lower"), Moderate: t("stock.risk.Moderate"), Elevated: t("stock.risk.Elevated") }[explanation.risk_level]}
                  </span>
                  <p>{explanation.summary}</p>
                </div>
                <div className="evidence-grid">
                  {explanation.evidence.map((item) => (
                    <article className="evidence-card" key={item.label}>
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                      <p>{item.interpretation}</p>
                    </article>
                  ))}
                </div>
                <div className="explanation-notes">
                  <div>
                    <h3>{t("stock.observations")}</h3>
                    <ul>{explanation.observations.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                  <div>
                    <h3>{t("stock.limits")}</h3>
                    <ul>{explanation.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                </div>
                <ResearchNotice>
                  {explanation.provider_message} {explanation.disclaimer}
                </ResearchNotice>
              </>
            ) : null}
          </Panel>

          <div className="two-column">
            <Panel title={t("stock.priceTitle", { ticker: data.ticker })} eyebrow={t("stock.chartEyebrow")} action={<span className="panel-meta">{instrument.currency} · {data.risk.observations.toLocaleString(numberLocale)} {t("stock.observationsCount")}</span>}>
              <PriceChart data={data.prices} />
            </Panel>
            <Panel title={t("stock.factorTitle")} eyebrow={t("stock.factorEyebrow")}>
              <div className="score-ring" style={{ "--score": `${data.factor_score.total}%` } as CSSProperties}>
                <div><strong>{data.factor_score.total.toFixed(0)}</strong><span>{t("stock.of100")}</span></div>
              </div>
              {[
                [t("stock.value"), data.factor_score.value],
                [t("stock.momentum"), data.factor_score.momentum],
                [t("stock.quality"), data.factor_score.quality],
              ].map(([label, score]) => (
                <div className="score-row" key={String(label)}>
                  <span>{label}</span>
                  <div className="score-track"><span style={{ width: `${score}%` }} /></div>
                  <strong>{Number(score).toFixed(1)}</strong>
                </div>
              ))}
              <ResearchNotice>
                {t("stock.factorNotice", {
                  rank: data.factor_score.rank,
                  size: data.factor_score.universe_size,
                  universe: factorUniverseLabel,
                  coverage: percent(data.factor_score.data_coverage),
                })}
              </ResearchNotice>
              <ResearchNotice>
                {t("stock.peerBasis", {
                  method: t(peerMethodKey),
                  sector: sectorLabel,
                  cap: peerCapKey ? t(peerCapKey) : t("stock.peerUnknown"),
                })}
              </ResearchNotice>
              {!factorMarketMatched ? (
                <ResearchNotice>{t("stock.factorFallback")}</ResearchNotice>
              ) : null}
            </Panel>
          </div>

          {data.factor_score.peer_rankings?.length ? (
            <Panel
              title={t("stock.peerTableTitle")}
              eyebrow={t("stock.peerTableEyebrow")}
              action={<button className="secondary-button" onClick={exportFactorTable} type="button">{t("stock.exportPeers")}</button>}
            >
              <div className="table-scroll">
                <table className="data-table factor-ranking-table">
                  <thead>
                    <tr>
                      <th>{t("stock.rank")}</th>
                      <th>{t("stock.ticker")}</th>
                      <th>{t("stock.value")}</th>
                      <th>{t("stock.momentum")}</th>
                      <th>{t("stock.quality")}</th>
                      <th>{t("stock.totalScore")}</th>
                      <th>{t("stock.coverage")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.factor_score.peer_rankings.map((row) => (
                      <tr className={row.ticker === data.ticker ? "target-row" : undefined} key={row.ticker}>
                        <td>{row.rank}</td>
                        <td><strong>{row.ticker}</strong></td>
                        <td>{row.value_score.toFixed(1)}</td>
                        <td>{row.momentum_score.toFixed(1)}</td>
                        <td>{row.quality_score.toFixed(1)}</td>
                        <td><strong>{row.quant_score.toFixed(1)}</strong></td>
                        <td>{percent(row.data_coverage)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ResearchNotice>{t("stock.factorNotice", {
                rank: data.factor_score.rank,
                size: data.factor_score.universe_size,
                universe: factorUniverseLabel,
                coverage: percent(data.factor_score.data_coverage),
              })}</ResearchNotice>
            </Panel>
          ) : null}

          <div className="two-column two-equal">
            <Panel
              title={t("stock.contributionTitle")}
              eyebrow={t("stock.contributionEyebrow")}
            >
              <FactorContributionChart
                value={data.factor_score.value}
                momentum={data.factor_score.momentum}
                quality={data.factor_score.quality}
                total={data.factor_score.total}
                labels={{
                  value: t("stock.value"),
                  momentum: t("stock.momentum"),
                  quality: t("stock.quality"),
                  total: t("stock.totalScore"),
                  contributionAxis: t("stock.contributionAxis"),
                }}
              />
              <ResearchNotice>{t("stock.contributionNotice")}</ResearchNotice>
            </Panel>
            <Panel
              title={t("stock.valuationDistributionTitle")}
              eyebrow={t("stock.valuationDistributionEyebrow")}
            >
              <ValuationDistributionChart
                rankings={data.factor_score.peer_rankings ?? []}
                target={data.ticker}
                unavailableLabel={t("stock.valuationUnavailable")}
              />
              <ResearchNotice>{t("stock.valuationDistributionNotice", { ticker: data.ticker })}</ResearchNotice>
            </Panel>
          </div>

          <div className="two-column two-equal">
            <Panel title={t("stock.metricsTitle")} eyebrow={t("stock.metricsEyebrow")}>
              <div className="definition-grid">
                <div className="definition-item"><span>{t("stock.pe")}</span><strong>{number(data.fundamentals.pe_ratio)}</strong></div>
                <div className="definition-item"><span>{t("stock.pb")}</span><strong>{number(data.fundamentals.pb_ratio)}</strong></div>
                <div className="definition-item"><span>EV / EBITDA</span><strong>{number(data.fundamentals.ev_to_ebitda)}</strong></div>
                <div className="definition-item"><span>{t("stock.roe")}</span><strong>{data.fundamentals.roe === null ? "N/A" : percent(data.fundamentals.roe)}</strong></div>
                <div className="definition-item"><span>{t("stock.margin")}</span><strong>{data.fundamentals.profit_margin === null ? "N/A" : percent(data.fundamentals.profit_margin)}</strong></div>
                <div className="definition-item"><span>{t("stock.debtRatio")}</span><strong>{data.fundamentals.debt_ratio === null ? "N/A" : percent(data.fundamentals.debt_ratio)}</strong></div>
                <div className="definition-item"><span>{t("stock.var")}</span><strong>{percent(data.risk.value_at_risk)}</strong></div>
              </div>
            </Panel>
            <Panel title={t("stock.mlTitle")} eyebrow={t("stock.mlEyebrow")} action={<span className="tag">{t("stock.researchOnly")}</span>}>
              {data.ml_experiment.status === "available" ? (
                <table className="data-table">
                  <thead><tr><th>{t("stock.model")}</th><th>RMSE</th><th>MAE</th><th>{t("stock.direction")}</th></tr></thead>
                  <tbody>
                    {data.ml_experiment.models.map((model) => (
                      <tr key={model.model}>
                        <td>{model.model}</td><td>{model.rmse.toFixed(5)}</td><td>{model.mae.toFixed(5)}</td><td>{percent(model.direction_accuracy)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="empty-state"><div><strong>{t("stock.noStudy")}</strong><p>{t("stock.mlUnavailable")}</p></div></div>}
              <ResearchNotice>{data.ml_experiment.status === "available" ? t("stock.mlAvailable") : t("stock.mlUnavailable")}</ResearchNotice>
            </Panel>
          </div>
        </>
      ) : null}
    </>
  );
}
