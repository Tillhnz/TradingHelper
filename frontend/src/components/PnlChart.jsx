import { useEffect, useRef, useState } from "react";
import { createChart, LineStyle } from "lightweight-charts";
import { finePointer, LockButton } from "./PriceChart.jsx";
import { alpha, C, FONT } from "../theme.js";

/** Gewinn/Verlust über die Zeit: Fläche über null grün, darunter rot. Gesperrt, bis man entsperrt. */
/** lines: weitere Vergleichslinien [{ points, color, title }]. */
export default function PnlChart({ points, height = 260, lines = null }) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const [locked, setLocked] = useState(true);

  useEffect(() => {
    const fine = finePointer();
    chartRef.current?.applyOptions(locked
      ? { handleScroll: { mouseWheel: false, pressedMouseMove: fine, horzTouchDrag: false, vertTouchDrag: false },
        handleScale: { mouseWheel: false, pinch: false, axisPressedMouseMove: fine } }
      : { handleScroll: true, handleScale: true });
  }, [locked]);

  useEffect(() => {
    if (!points?.length) return undefined;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: "rgba(0, 0, 0, 0)" }, textColor: C.text, fontFamily: FONT },
      grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
      rightPriceScale: { borderColor: C.line },
      timeScale: { borderColor: C.line },
      handleScroll: { mouseWheel: false, pressedMouseMove: finePointer(), horzTouchDrag: false, vertTouchDrag: false },
      handleScale: { mouseWheel: false, pinch: false, axisPressedMouseMove: finePointer() },
    });
    chartRef.current = chart;
    const s = chart.addBaselineSeries({
      baseValue: { type: "price", price: 0 },
      topLineColor: C.up, topFillColor1: alpha("up", 0.35), topFillColor2: alpha("up", 0.04),
      bottomLineColor: C.down, bottomFillColor1: alpha("down", 0.04), bottomFillColor2: alpha("down", 0.35),
      lineWidth: 2, priceLineVisible: false,
    });
    s.setData(points);
    for (const l of lines || []) {
      if (!l.points?.length) continue;
      const ls = chart.addLineSeries({ color: l.color, lineWidth: 2, lineStyle: l.dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false, lastValueVisible: false, title: l.title || "" });
      ls.setData(l.points);
    }
    s.createPriceLine({ price: 0, color: C.neutral, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false });
    chart.timeScale().fitContent();
    return () => { chart.remove(); chartRef.current = null; };
  }, [points, lines]);

  return (
    <div className={`chart-stack ${locked ? "is-locked" : "is-unlocked"}`}>
      <LockButton locked={locked} onToggle={() => setLocked((l) => !l)} />
      <div ref={ref} style={{ height }} />
    </div>
  );
}
