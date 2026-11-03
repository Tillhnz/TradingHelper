import { useEffect, useRef } from "react";
import { createChart, CrosshairMode, LineStyle } from "lightweight-charts";

const COLORS = {
  bg: "#0e1620", text: "#8d9eb0", grid: "#1b2a3a", line: "#263749",
  up: "#6fd3c3", down: "#ff6b6b", amber: "#f2b84b",
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

/** Erste Kerze ab Zeitpunkt t (Marker müssen auf einer vorhandenen Kerze liegen). */
function snap(rows, t) {
  const hit = rows.find((r) => r.time >= t);
  return hit ? hit.time : null;
}

const dayStart = (iso) => Math.floor(new Date(`${iso}T00:00:00Z`).getTime() / 1000);

/**
 * Kerzenchart mit Volumen, Durchschnitten, Bollinger und darunter RSI und MACD.
 * Overlays: Signal-Marker (events), Linien des Einstiegsplans (planLines) und eigene Positionen mit grüner
 * Gewinn- und roter Verlustzone ab dem Kaufkurs.
 */
export default function PriceChart({ rows, showSma = true, showBb = false, events = [], planLines = [], positions = [], onVisibleRange }) {
  const mainRef = useRef(null);
  const rsiRef = useRef(null);
  const macdRef = useRef(null);
  const rangeRef = useRef(null);

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

    // Eigene Positionen: Fläche zwischen Kurs und Kaufkurs, grün darüber, rot darunter
    const markers = [];
    positions.forEach((p) => {
      const from = dayStart(p.buy_date);
      const to = p.sell_date ? dayStart(p.sell_date) + 86399 : Infinity;
      const seg = rows.filter((r) => r.time >= from && r.time <= to);
      if (!seg.length || !p.buy_price) return;
      const area = main.addBaselineSeries({
        baseValue: { type: "price", price: p.buy_price },
        topLineColor: "rgba(111, 211, 195, 0.9)", topFillColor1: "rgba(111, 211, 195, 0.32)", topFillColor2: "rgba(111, 211, 195, 0.04)",
        bottomLineColor: "rgba(255, 107, 107, 0.9)", bottomFillColor1: "rgba(255, 107, 107, 0.04)", bottomFillColor2: "rgba(255, 107, 107, 0.32)",
        lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      });
      area.setData(seg.map((r) => ({ time: r.time, value: r.close })));
      area.createPriceLine({ price: p.buy_price, color: COLORS.amber, lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: `Kauf ${p.quantity}×` });
      if (!p.sell_date) {
        if (p.stop) area.createPriceLine({ price: p.stop, color: COLORS.down, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "Stopp" });
        if (p.target) area.createPriceLine({ price: p.target, color: COLORS.up, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "Ziel" });
      }
      const tb = snap(rows, from);
      if (tb) markers.push({ time: tb, position: "belowBar", color: COLORS.amber, shape: "arrowUp", text: "Kauf" });
      if (p.sell_date) {
        const ts = snap(rows, dayStart(p.sell_date));
        if (ts) markers.push({ time: ts, position: "aboveBar", color: COLORS.amber, shape: "arrowDown", text: "Verkauf" });
      }
    });

    // Vergangene Entscheidungspunkte; Beschriftung nur an den jüngsten, damit der Chart lesbar bleibt
    const labelFrom = events.length - 8;
    events.forEach((e, i) => {
      const t = snap(rows, e.time);
      if (t === null || t - e.time > 7 * 86400) return;
      const text = i >= labelFrom ? e.label : "";
      markers.push(e.side === "buy"
        ? { time: t, position: "belowBar", color: COLORS.up, shape: "arrowUp", text }
        : { time: t, position: "aboveBar", color: COLORS.down, shape: "arrowDown", text });
    });
    markers.sort((a, b) => a.time - b.time);
    candles.setMarkers(markers);

    // Einstiegsplan: Kursmarken als waagerechte Linien
    planLines.filter((l) => l.price).forEach((l) => {
      candles.createPriceLine({ price: l.price, color: l.color, lineWidth: l.width || 1, lineStyle: l.style ?? LineStyle.Dashed, axisLabelVisible: true, title: l.title });
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
      if (c === main) { rangeRef.current = range; onVisibleRange?.(range); }
    }));
    // Beim automatischen Nachladen den Ausschnitt behalten, sonst die letzten ~160 Kerzen zeigen
    if (rangeRef.current) {
      main.timeScale().setVisibleLogicalRange(rangeRef.current);
    } else {
      const visible = Math.min(rows.length, 160);
      main.timeScale().setVisibleLogicalRange({ from: rows.length - visible, to: rows.length + 3 });
    }

    return () => charts.forEach((c) => c.remove());
  }, [rows, showSma, showBb, events, planLines, positions, onVisibleRange]);

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
