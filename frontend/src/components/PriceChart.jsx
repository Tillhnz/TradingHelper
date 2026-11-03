import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode, LineStyle } from "lightweight-charts";

const COLORS = {
  bg: "#111b26", text: "#8d9eb0", grid: "#1a2735", line: "#263749",
  up: "#6fd3c3", down: "#ff6b6b", amber: "#f2b84b",
  sma20: "#f2b84b", sma50: "#7aa7ff", sma200: "#c792ea",
  bb: "#5d7389", rsi: "#f2b84b", macd: "#7aa7ff", signal: "#ff9f6b",
};

const interaction = (locked) => ({
  handleScroll: !locked,
  handleScale: !locked,
  kineticScroll: { touch: !locked, mouse: false },
});

const baseOptions = (locked) => ({
  autoSize: true,
  layout: { background: { color: COLORS.bg }, textColor: COLORS.text, fontFamily: "Barlow, system-ui, sans-serif" },
  grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
  rightPriceScale: { borderColor: COLORS.line },
  timeScale: { borderColor: COLORS.line, timeVisible: true, secondsVisible: false },
  crosshair: { mode: CrosshairMode.Normal },
  ...interaction(locked),
});

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

/** Sperre gegen versehentliches Verschieben beim Scrollen der Seite (v. a. am Handy). */
export function LockButton({ locked, onToggle }) {
  return (
    <button type="button" className={`chart-lock ${locked ? "" : "open"}`} onClick={onToggle}
      aria-pressed={!locked} title={locked ? "Chart entsperren, um zu verschieben und zu zoomen" : "Chart wieder sperren"}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        {locked ? <path d="M7 11 V8 A5 5 0 0 1 17 8 V11 M5 11 H19 V21 H5 Z" /> : <path d="M7 11 V8 A5 5 0 0 1 16.5 6 M5 11 H19 V21 H5 Z" />}
      </svg>
      {locked ? "Zum Verschieben entsperren" : "Sperren"}
    </button>
  );
}

/**
 * Kurschart. Einfach: Fläche des Schlusskurses. Profi: Kerzen mit Volumen, Durchschnitten, Bollinger, darunter RSI
 * und MACD. Overlays: Signal-Marker, Linien des Einstiegsplans und eigene Käufe mit Gewinn-/Verlustzone.
 * Standardmäßig gesperrt, damit Wischen die Seite scrollt und nicht den Chart verschiebt.
 */
export default function PriceChart({ rows, simple = false, showSma = true, showBb = false, events = [], planLines = [], positions = [] }) {
  const mainRef = useRef(null);
  const rsiRef = useRef(null);
  const macdRef = useRef(null);
  const rangeRef = useRef(null);
  const chartsRef = useRef([]);
  const [locked, setLocked] = useState(true);
  const lockedRef = useRef(true);

  useEffect(() => {
    lockedRef.current = locked;
    chartsRef.current.forEach((c) => c.applyOptions(interaction(locked)));
  }, [locked]);

  useEffect(() => {
    if (!rows?.length) return undefined;
    const opts = baseOptions(lockedRef.current);
    const main = createChart(mainRef.current, opts);
    let priceSeries;
    if (simple) {
      const up = rows[rows.length - 1].close >= rows[0].close;
      priceSeries = main.addAreaSeries({
        lineColor: up ? COLORS.up : COLORS.down, lineWidth: 2,
        topColor: up ? "rgba(111, 211, 195, 0.28)" : "rgba(255, 107, 107, 0.25)", bottomColor: "rgba(17, 27, 38, 0)",
        priceLineVisible: true, priceLineColor: "#5d7389",
      });
      priceSeries.setData(rows.map((r) => ({ time: r.time, value: r.close })));
    } else {
      priceSeries = main.addCandlestickSeries({
        upColor: COLORS.up, downColor: COLORS.down, borderVisible: false, wickUpColor: COLORS.up, wickDownColor: COLORS.down,
      });
      priceSeries.setData(rows.map((r) => ({ time: r.time, open: r.open, high: r.high, low: r.low, close: r.close })));
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
    }

    // Eigene Käufe: Fläche zwischen Kurs und Kaufkurs, grün darüber, rot darunter
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

    // Vergangene Entscheidungspunkte; Beschriftung nur im Profi-Modus und nur an den jüngsten
    const labelFrom = simple ? Infinity : events.length - 8;
    events.forEach((e, i) => {
      const t = snap(rows, e.time);
      if (t === null || t - e.time > 7 * 86400) return;
      const text = i >= labelFrom ? e.label : "";
      markers.push(e.side === "buy"
        ? { time: t, position: "belowBar", color: COLORS.up, shape: "arrowUp", text }
        : { time: t, position: "aboveBar", color: COLORS.down, shape: "arrowDown", text });
    });
    markers.sort((a, b) => a.time - b.time);
    priceSeries.setMarkers(markers);

    planLines.filter((l) => l.price).forEach((l) => {
      priceSeries.createPriceLine({ price: l.price, color: l.color, lineWidth: l.width || 1, lineStyle: l.style ?? LineStyle.Dashed, axisLabelVisible: true, title: l.title });
    });

    const charts = [main];
    if (!simple) {
      const rsiChart = createChart(rsiRef.current, opts);
      const rsi = line(rsiChart, rows, "rsi", COLORS.rsi, 2);
      [70, 30].forEach((p) => rsi.createPriceLine({ price: p, color: "#5d7389", lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false }));
      const macdChart = createChart(macdRef.current, opts);
      const hist = macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
      hist.setData(rows.filter((r) => r.hist !== null).map((r) => ({ time: r.time, value: r.hist, color: r.hist >= 0 ? COLORS.up : COLORS.down })));
      line(macdChart, rows, "macd", COLORS.macd);
      line(macdChart, rows, "signal", COLORS.signal);
      charts.push(rsiChart, macdChart);
    }
    chartsRef.current = charts;

    let syncing = false;
    charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range || syncing) return;
      syncing = true;
      charts.forEach((o) => { if (o !== c) o.timeScale().setVisibleLogicalRange(range); });
      syncing = false;
      if (c === main) rangeRef.current = range;
    }));
    if (rangeRef.current) {
      main.timeScale().setVisibleLogicalRange(rangeRef.current);
    } else if (simple) {
      main.timeScale().fitContent();
    } else {
      const visible = Math.min(rows.length, 160);
      main.timeScale().setVisibleLogicalRange({ from: rows.length - visible, to: rows.length + 3 });
    }

    return () => { charts.forEach((c) => c.remove()); chartsRef.current = []; };
  }, [rows, simple, showSma, showBb, events, planLines, positions]);

  return (
    <div className={`chart-stack ${locked ? "is-locked" : "is-unlocked"}`}>
      <LockButton locked={locked} onToggle={() => setLocked((l) => !l)} />
      <div className={`chart-main ${simple ? "simple" : ""}`} ref={mainRef} />
      {!simple && (
        <>
          <div className="chart-pane-label">RSI 14</div>
          <div className="chart-pane" ref={rsiRef} />
          <div className="chart-pane-label">MACD 12/26/9</div>
          <div className="chart-pane" ref={macdRef} />
        </>
      )}
    </div>
  );
}
