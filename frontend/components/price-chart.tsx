"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  type CandlestickData,
  type HistogramData,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { PricePoint } from "@/types/api";

export function PriceChart({ data }: { data: PricePoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || data.length === 0) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 430,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#8f9bad",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.11)" },
        horzLines: { color: "rgba(148, 163, 184, 0.11)" },
      },
      rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.18)" },
      timeScale: { borderColor: "rgba(148, 163, 184, 0.18)", timeVisible: true },
      crosshair: {
        vertLine: { color: "rgba(240, 162, 58, 0.44)", labelBackgroundColor: "#b77828" },
        horzLine: { color: "rgba(240, 162, 58, 0.44)", labelBackgroundColor: "#b77828" },
      },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#16845b",
      downColor: "#c4475d",
      borderVisible: false,
      wickUpColor: "#16845b",
      wickDownColor: "#c4475d",
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    candles.setData(
      data.map<CandlestickData>((point) => ({
        time: point.date as Time,
        open: point.open,
        high: point.high,
        low: point.low,
        close: point.close,
      })),
    );
    volume.setData(
      data.map<HistogramData>((point) => ({
        time: point.date as Time,
        value: point.volume,
        color: point.close >= point.open ? "rgba(22, 132, 91, 0.24)" : "rgba(196, 71, 93, 0.24)",
      })),
    );
    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth });
    });
    resizeObserver.observe(container);
    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [data]);

  return <div className="price-chart" ref={containerRef} />;
}
