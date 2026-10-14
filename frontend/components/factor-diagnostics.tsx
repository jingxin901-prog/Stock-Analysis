"use client";

import type { Data } from "plotly.js";

import { PlotlyChart } from "@/components/plotly-chart";
import type { FactorPeerRanking, FactorValidationPoint } from "@/types/api";

type FactorLabels = {
  value: string;
  momentum: string;
  quality: string;
  total: string;
  contributionAxis: string;
};

export function FactorContributionChart({
  value,
  momentum,
  quality,
  total,
  labels,
}: {
  value: number;
  momentum: number;
  quality: number;
  total: number;
  labels: FactorLabels;
}) {
  const contributions = [value / 3, momentum / 3, quality / 3];
  const trace = {
    type: "waterfall",
    x: [labels.value, labels.momentum, labels.quality, labels.total],
    y: [...contributions, 0],
    measure: ["relative", "relative", "relative", "total"],
    text: [
      ...contributions.map((score) => `+${score.toFixed(1)}`),
      total.toFixed(1),
    ],
    textposition: "outside",
    cliponaxis: false,
    connector: { line: { color: "rgba(148, 163, 184, 0.32)", width: 1 } },
    increasing: { marker: { color: "#d08a31" } },
    totals: { marker: { color: "#4f8fca" } },
    hovertemplate: "%{x}: %{text} points<extra></extra>",
  } as Data;

  return (
    <div className="chart-medium">
      <PlotlyChart
        data={[trace]}
        layout={{
          showlegend: false,
          margin: { l: 52, r: 24, t: 36, b: 54 },
          xaxis: { fixedrange: true },
          yaxis: {
            title: { text: labels.contributionAxis },
            range: [0, 105],
            gridcolor: "rgba(148,163,184,.12)",
            fixedrange: true,
          },
        }}
      />
    </div>
  );
}

const VALUATION_METRICS = [
  ["pe_ratio", "PE"],
  ["pb_ratio", "PB"],
  ["ev_to_ebitda", "EV / EBITDA"],
] as const;

export function ValuationDistributionChart({
  rankings,
  target,
  unavailableLabel,
}: {
  rankings: FactorPeerRanking[];
  target: string;
  unavailableLabel: string;
}) {
  return (
    <div className="valuation-small-multiples">
      {VALUATION_METRICS.map(([field, label]) => {
        const observations = rankings
          .map((row) => ({ ticker: row.ticker, value: row[field] }))
          .filter(
            (row): row is { ticker: string; value: number } =>
              row.value !== null && Number.isFinite(row.value) && row.value > 0,
          );
        const peers = observations.filter((row) => row.ticker !== target);
        const targetObservation = observations.find((row) => row.ticker === target);
        const data: Data[] = [];
        if (peers.length) {
          data.push({
            type: "box",
            x: peers.map((row) => row.value),
            y: peers.map(() => label),
            name: label,
            orientation: "h",
            boxpoints: "all",
            jitter: 0.45,
            pointpos: 0,
            marker: { color: "#718096", size: 7, opacity: 0.85 },
            line: { color: "#8693a5", width: 1 },
            hovertext: peers.map((row) => row.ticker),
            hovertemplate: "%{hovertext}<br>%{x:.2f}<extra></extra>",
          } as Data);
        }
        if (targetObservation) {
          data.push({
            type: "scatter",
            mode: "markers",
            x: [targetObservation.value],
            y: [label],
            name: target,
            marker: {
              color: "#f0a23a",
              size: 12,
              symbol: "diamond",
              line: { color: "#ffffff", width: 1 },
            },
            hovertemplate: `${target}<br>%{x:.2f}<extra></extra>`,
          } as Data);
        }
        return (
          <div className="valuation-mini" key={field}>
            <strong>{label}</strong>
            {data.length ? (
              <div className="valuation-mini-chart">
                <PlotlyChart
                  data={data}
                  layout={{
                    showlegend: false,
                    margin: { l: 18, r: 18, t: 12, b: 42 },
                    xaxis: {
                      gridcolor: "rgba(148,163,184,.12)",
                      rangemode: "tozero",
                      fixedrange: true,
                    },
                    yaxis: { visible: false, fixedrange: true },
                    hovermode: "closest",
                  }}
                />
              </div>
            ) : (
              <div className="valuation-empty">{unavailableLabel}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function MomentumValidationChart({
  path,
  labels,
}: {
  path: FactorValidationPoint[];
  labels: {
    gross: string;
    net: string;
    equalWeight: string;
    valueAxis: string;
  };
}) {
  const dates = path.length
    ? [path[0].formation_date, ...path.map((point) => point.date)]
    : [];
  const trace = (
    name: string,
    values: number[],
    color: string,
    dash: "solid" | "dot" = "solid",
  ) => ({
    type: "scatter",
    mode: "lines",
    name,
    x: dates,
    y: [1, ...values].map((value) => value * 100),
    line: { color, width: 2, dash },
    hovertemplate: `%{x}<br>${name}: %{y:.1f}<extra></extra>`,
  }) as Data;

  return (
    <div className="chart-medium">
      <PlotlyChart
        data={[
          trace(labels.gross, path.map((point) => point.gross_value), "#d08a31"),
          trace(labels.net, path.map((point) => point.net_value), "#4f8fca"),
          trace(
            labels.equalWeight,
            path.map((point) => point.equal_weight_value),
            "#8492a6",
            "dot",
          ),
        ]}
        layout={{
          hovermode: "x unified",
          legend: { orientation: "h", x: 0, y: 1.12 },
          margin: { l: 62, r: 24, t: 44, b: 48 },
          xaxis: { gridcolor: "rgba(148,163,184,.08)" },
          yaxis: {
            title: { text: labels.valueAxis },
            gridcolor: "rgba(148,163,184,.12)",
            rangemode: "tozero",
          },
        }}
      />
    </div>
  );
}
