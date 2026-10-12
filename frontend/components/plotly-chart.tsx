"use client";

import dynamic from "next/dynamic";
import type { Config, Data, Layout } from "plotly.js";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export function PlotlyChart({
  data,
  layout,
}: {
  data: Data[];
  layout: Partial<Layout>;
}) {
  const config: Partial<Config> = {
    displaylogo: false,
    responsive: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
  };
  return (
    <Plot
      className="plotly-chart"
      config={config}
      data={data}
      layout={{
        autosize: true,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#91a0b2", family: "Avenir Next, Inter, ui-sans-serif, system-ui" },
        margin: { l: 56, r: 24, t: 24, b: 48 },
        ...layout,
      }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
