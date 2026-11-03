import { useEffect, useRef } from "react";
import { createChart, LineStyle } from "lightweight-charts";

/** Gewinn/Verlust über die Zeit: Fläche über null grün, darunter rot. */
export default function PnlChart({ points, height = 260 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!points?.length) return undefined;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: "#16222f" }, textColor: "#8d9eb0", fontFamily: "Barlow, system-ui, sans-serif" },
      grid: { vertLines: { color: "#1b2a3a" }, horzLines: { color: "#1b2a3a" } },
      rightPriceScale: { borderColor: "#263749" },
      timeScale: { borderColor: "#263749" },
    });
    const s = chart.addBaselineSeries({
      baseValue: { type: "price", price: 0 },
      topLineColor: "#6fd3c3", topFillColor1: "rgba(111, 211, 195, 0.35)", topFillColor2: "rgba(111, 211, 195, 0.04)",
      bottomLineColor: "#ff6b6b", bottomFillColor1: "rgba(255, 107, 107, 0.04)", bottomFillColor2: "rgba(255, 107, 107, 0.35)",
      lineWidth: 2, priceLineVisible: false,
    });
    s.setData(points);
    s.createPriceLine({ price: 0, color: "#5d7389", lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points]);
  return <div ref={ref} style={{ height }} />;
}
