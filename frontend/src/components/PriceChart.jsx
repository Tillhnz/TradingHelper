import { useEffect, useRef } from "react";
import { createChart, CrosshairMode, LineStyle } from "lightweight-charts";

const COLORS = {
  bg: "#0e1620", text: "#8d9eb0", grid: "#1b2a3a", line: "#263749",
  up: "#6fd3c3", down: "#ff6b6b",
  sma20: "#f2b84b", sma50: "#7aa7ff", sma200: "#c792ea",
  bb: "#5d7389", rsi: "#f2b84b", macd: "#7aa7ff", signal: "#ff9f6b",
};

const baseOptions = {
  autoSize: true,
  layout: { background: { color: COLORS.bg }, textColor: COLORS.text, fontFamily: "Barlow, system-ui, sans-serif" },
  grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
  rightPriceScale: { borderColor: COLORS.line },
  timeScale: { borderColor: COLORS.line, timeVisible: true, secondsVisible: false },
  crosshair: { mode: CrosshairMode.Normal },
};

function line(chart, rows, field, color, width = 1) {
  const s = chart.addLineSeries({ color, lineWidth: width, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
  s.setData(rows.filter((r) => r[field] !== null && r[field] !== undefined).map((r) => ({ time: r.time, value: r[field] })));
  return s;
}

/** Kerzenchart mit Volumen, gleitenden Durchschnitten und Bollinger, darunter RSI und MACD (zeitlich gekoppelt). */
export default function PriceChart({ rows, showSma = true, showBb = false, levels = [] }) {
  const mainRef = useRef(null);
  const rsiRef = useRef(null);
  const macdRef = useRef(null);

  useEffect(() => {
    if (!rows?.length) return undefined;

    const main = createChart(mainRef.current, baseOptions);
    const candles = main.addCandlestickSeries({
      upColor: COLORS.up, downColor: COLORS.down, borderVisible: false, wickUpColor: COLORS.up, wickDownColor: COLORS.down,
    });
    candles.setData(rows.map((r) => ({ time: r.time, open: r.open, high: r.high, low: r.low, close: r.close })));
    const vol = main.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false });
    main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(rows.map((r) => ({ time: r.time, value: r.volume ?? 0, color: r.close >= r.open ? "#6fd3c344" : "#ff6b6b44" })));
    if (showSma) {
      line(main, rows, "sma20", COLORS.sma20);
      line(main, rows, "sma50", COLORS.sma50);
      line(main, rows, "sma200", COLORS.sma200, 2);
    }
    if (showBb) {
      line(main, rows, "bb_upper", COLORS.bb);
      line(main, rows, "bb_mid", COLORS.bb);
      line(main, rows, "bb_lower", COLORS.bb);
    }
    levels.filter((l) => l.price).forEach((l) => {
      candles.createPriceLine({ price: l.price, color: l.color, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: l.title });
    });

    const rsiChart = createChart(rsiRef.current, baseOptions);
    const rsi = line(rsiChart, rows, "rsi", COLORS.rsi, 2);
    [70, 30].forEach((p) => rsi.createPriceLine({ price: p, color: "#5d7389", lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false }));

    const macdChart = createChart(macdRef.current, baseOptions);
    const hist = macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
    hist.setData(rows.filter((r) => r.hist !== null).map((r) => ({ time: r.time, value: r.hist, color: r.hist >= 0 ? COLORS.up : COLORS.down })));
    line(macdChart, rows, "macd", COLORS.macd);
    line(macdChart, rows, "signal", COLORS.signal);

    const charts = [main, rsiChart, macdChart];
    let syncing = false;
    charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range || syncing) return;
      syncing = true;
      charts.forEach((o) => { if (o !== c) o.timeScale().setVisibleLogicalRange(range); });
      syncing = false;
    }));
    const visible = Math.min(rows.length, 160);
    main.timeScale().setVisibleLogicalRange({ from: rows.length - visible, to: rows.length + 3 });

    return () => charts.forEach((c) => c.remove());
  }, [rows, showSma, showBb, levels]);

  return (
    <div className="chart-stack">
      <div className="chart-main" ref={mainRef} />
      <div className="chart-pane-label">RSI 14</div>
      <div className="chart-pane" ref={rsiRef} />
      <div className="chart-pane-label">MACD 12/26/9</div>
      <div className="chart-pane" ref={macdRef} />
    </div>
  );
}
