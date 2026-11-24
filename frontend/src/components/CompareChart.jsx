import { useEffect, useRef, useState } from "react";
import { createChart, LineStyle } from "lightweight-charts";
import { baseOptions } from "./PriceChart.jsx";
import { C } from "../theme.js";
import { money, pct } from "../fmt.js";

/* Mehrere Linien auf einer Achse (Depot gegen Indizes). Crosshair mit Werten aller Linien in der Legende darüber.
   series: [{ id, label, color, values: number[], dashed? }], dates: "YYYY-MM-DD"[] */
export default function CompareChart({ dates, series, mode = "index", currency = "EUR", height = 300 }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    if (!dates?.length || !ref.current) return undefined;
    const chart = createChart(ref.current, {
      ...baseOptions(true, false),
      height,
      rightPriceScale: { borderColor: C.line, scaleMargins: { top: 0.08, bottom: 0.05 } },
      localization: {
        locale: "de-DE",
        priceFormatter: (v) => (mode === "index" ? pct(v - 100, 1) : money(v, currency)),
        timeFormatter: (t) => new Date(t * 1000).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }),
      },
    });
    const times = dates.map((d) => Math.floor(Date.parse(`${d}T00:00:00Z`) / 1000));
    const made = series.map((s) => {
      const line = chart.addLineSeries({
        color: s.color, lineWidth: s.width || 2, lineStyle: s.dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false, lastValueVisible: !s.dashed, crosshairMarkerRadius: 4,
      });
      line.setData(times.map((t, i) => ({ time: t, value: s.values[i] })).filter((p) => p.value != null));
      return [s, line];
    });
    if (mode === "index") {
      made[0]?.[1].createPriceLine({ price: 100, color: C.neutral, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: false });
    }
    chart.timeScale().fitContent();
    chart.subscribeCrosshairMove((p) => {
      if (!p?.time || !p.seriesData) { setHover(null); return; }
      const vals = {};
      made.forEach(([s, line]) => { const d = p.seriesData.get(line); if (d) vals[s.id] = d.value; });
      setHover({ time: p.time, vals });
    });
    return () => chart.remove();
  }, [dates, series, mode, currency, height]);

  const last = (s) => [...s.values].reverse().find((v) => v != null);
  const fmt = (v) => (v == null ? "–" : mode === "index" ? pct(v - 100, 1) : money(v, currency));
  return (
    <div className="compare-chart">
      <ul className="compare-legend" aria-live="polite">
        <li className="when">{hover ? new Date(hover.time * 1000).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }) : "heute"}</li>
        {series.map((s) => (
          <li key={s.id}><i style={{ background: s.color, opacity: s.dashed ? 0.6 : 1 }} />{s.label} <strong>{fmt(hover ? hover.vals[s.id] : last(s))}</strong></li>
        ))}
      </ul>
      <div ref={ref} style={{ height }} />
    </div>
  );
}
