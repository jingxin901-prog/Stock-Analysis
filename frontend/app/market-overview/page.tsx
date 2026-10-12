"use client";

import type { Data } from "plotly.js";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { PlotlyChart } from "@/components/plotly-chart";
import { Sparkline } from "@/components/sparkline";
import { ErrorBanner, LoadingState, Panel, ResearchNotice } from "@/components/ui";
import { getApiErrorMessage, getMarketOverview } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { MarketOverviewResponse } from "@/types/api";

const chartColors = ["#f0a23a", "#4f8fca", "#a679c8", "#7f8c9d"];

function formatPrice(value: number, symbol: string, locale: string) {
  if (symbol === "BTC-USD") {
    return new Intl.NumberFormat(locale, { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
  }
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);
}

export default function MarketOverviewPage() {
  const [data, setData] = useState<MarketOverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestVersion, setRequestVersion] = useState(0);
  const { locale, t } = useI18n();
  const numberLocale = locale === "zh" ? "zh-CN" : "en-US";
  const instrumentNames = useMemo<Record<string, string>>(() => ({
    sp500: t("market.sp500"),
    nasdaq: t("market.nasdaq"),
    vix: t("market.vix"),
    bitcoin: t("market.bitcoin"),
  }), [t]);

  useEffect(() => {
    let active = true;
    getMarketOverview()
      .then((response) => {
        if (active) {
          setData(response);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(getApiErrorMessage(reason, t));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [requestVersion, t]);

  const comparisonData = useMemo<Data[]>(() => {
    if (!data) return [];
    return data.instruments.map((instrument, index) => {
      const initial = instrument.history[0]?.value ?? 1;
      return {
        type: "scatter",
        mode: "lines",
        name: instrumentNames[instrument.key] ?? instrument.name,
        x: instrument.history.map((point) => point.date),
        y: instrument.history.map((point) => ((point.value / initial) - 1) * 100),
        line: { color: chartColors[index], width: 1.8 },
        hovertemplate: "%{x}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
      };
    });
  }, [data, instrumentNames]);

  const status = loading
    ? { label: t("market.checking"), tone: "neutral" }
    : error || data?.status === "unavailable"
      ? { label: t("market.unavailable"), tone: "offline" }
      : data?.status === "partial"
        ? { label: t("market.partial"), tone: "warning" }
        : data?.source === "market-cache"
          ? { label: t("market.cached"), tone: "warning" }
          : data?.source === "mixed"
            ? { label: t("market.mixed"), tone: "warning" }
            : { label: t("market.connected"), tone: "complete" };
  const unavailableSymbols = data?.unavailable_instruments
    .map((instrument) => instrument.symbol)
    .join(", ") ?? "";
  const retryRequest = () => {
    setLoading(true);
    setError(null);
    setRequestVersion((version) => version + 1);
  };

  return (
    <>
      <PageHeader
        eyebrow={t("market.eyebrow")}
        title={t("market.title")}
        description={t("market.description")}
      />
      <div className="topline">
        <span>{t("market.window")}</span>
        <span className={`live-pill live-pill-${status.tone}`}>● {status.label}</span>
      </div>
      {error ? <ErrorBanner message={error} /> : null}
      {error ? (
        <div className="utility-actions market-retry">
          <button className="secondary-button" disabled={loading} onClick={retryRequest} type="button">
            {t("market.retry")}
          </button>
        </div>
      ) : null}
      {!data && loading && !error ? <LoadingState label={t("market.loading")} /> : null}
      {data ? (
        <>
          {data.unavailable_instruments.length > 0 ? (
            <ResearchNotice>
              {data.status === "unavailable"
                ? t("market.unavailableNotice")
                : t("market.partialNotice", {
                  available: data.instruments.length,
                  total: data.instruments.length + data.unavailable_instruments.length,
                  symbols: unavailableSymbols,
                })}
            </ResearchNotice>
          ) : null}
          {data.status !== "complete" && !error ? (
            <div className="utility-actions market-retry">
              <button
                className="secondary-button"
                disabled={loading}
                onClick={retryRequest}
                type="button"
              >
                {t("market.retry")}
              </button>
            </div>
          ) : null}
          <div className="market-grid">
            {data.instruments.map((instrument) => {
              const positive = instrument.change >= 0;
              return (
                <article className="market-card" key={instrument.key}>
                  <div className="market-card-header">
                    <div>
                      <h2>{instrumentNames[instrument.key] ?? instrument.name}</h2>
                      <span className="market-symbol">{instrument.symbol}</span>
                    </div>
                    <span className="market-symbol">
                      {instrument.as_of} · {instrument.served_from_cache ? t("market.cachedSource") : t("market.liveSource")}
                    </span>
                  </div>
                  <strong className="market-price">{formatPrice(instrument.latest_price, instrument.symbol, numberLocale)}</strong>
                  <span className={`change ${positive ? "change-positive" : "change-negative"}`}>
                    {positive ? "+" : ""}{instrument.change.toFixed(2)} · {positive ? "+" : ""}{(instrument.change_percent * 100).toFixed(2)}%
                  </span>
                  <Sparkline values={instrument.history.map((point) => point.value)} positive={positive} />
                </article>
              );
            })}
          </div>

          {data.instruments.length > 0 ? (
            <>
              <Panel title={t("market.paths")} eyebrow={t("market.relative")} action={<span className="panel-meta">{t("market.base")}</span>}>
                <div className="chart-tall">
                  <PlotlyChart
                    data={comparisonData}
                    layout={{
                      hovermode: "x unified",
                      legend: { orientation: "h", x: 0, y: 1.12 },
                      xaxis: { gridcolor: "rgba(148,163,184,.12)", zeroline: false },
                      yaxis: { title: { text: t("market.axis") }, gridcolor: "rgba(148,163,184,.12)", ticksuffix: "%" },
                    }}
                  />
                </div>
              </Panel>
              <ResearchNotice>
                {t("market.notice")}
              </ResearchNotice>
            </>
          ) : null}
        </>
      ) : null}
    </>
  );
}
