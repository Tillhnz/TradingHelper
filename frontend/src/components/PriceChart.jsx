import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode, LineStyle } from "lightweight-charts";
import { money, pct, signedMoney } from "../fmt.js";
import { barIndex, buyTimestamp, PositionBox, sellTimestamp } from "./positionBox.js";

export const COLORS = {
  bg: "rgba(0, 0, 0, 0)", text: "#9fb0c2", grid: "rgba(255, 255, 255, 0.05)", line: "rgba(255, 255, 255, 0.12)",
  up: "#6fd3c3", down: "#ff6b6b", amber: "#f2b84b",
  buySig: "#38bdf8", sellSig: "#e879f9",
  sma20: "#f2b84b", sma50: "#7aa7ff", sma200: "#c792ea",
  bb: "#5d7389", rsi: "#f2b84b", macd: "#7aa7ff", signal: "#ff9f6b",
};

// Maus/Touchpad (Laptop) oder Finger (Handy)? Am Laptop darf man im gesperrten Chart ziehen und an den Achsen
// zoomen, nur das Mausrad scrollt weiter die Seite. Am Handy ist gesperrt wirklich gesperrt.
export const finePointer = () => typeof window !== "undefined" && window.matchMedia?.("(pointer: fine)").matches;

const interaction = (locked) => {
  if (!locked) return { handleScroll: true, handleScale: true, kineticScroll: { touch: true, mouse: false } };
  const fine = finePointer();
  return {
    handleScroll: { mouseWheel: false, pressedMouseMove: fine, horzTouchDrag: false, vertTouchDrag: false },
    handleScale: { mouseWheel: false, pinch: false, axisPressedMouseMove: fine, axisDoubleClickReset: fine },
    kineticScroll: { touch: false, mouse: false },
  };
};

// lightweight-charts rechnet in UTC; Beschriftungen in Ortszeit des Browsers (wichtig für den Tagesverlauf)
const fmtTime = (t, opts) => new Date(t * 1000).toLocaleString("de-DE", opts);
const tickFormatter = (t, kind) => {
  if (typeof t !== "number") return null;
  if (kind === 0) return fmtTime(t, { year: "numeric" });
  if (kind === 1) return fmtTime(t, { month: "short" });
  if (kind === 2) return fmtTime(t, { day: "numeric", month: "numeric" });
  return fmtTime(t, { hour: "2-digit", minute: "2-digit" });
};

export const CHART_TYPES = [
  { id: "area", label: "Fläche" },
  { id: "line", label: "Linie" },
  { id: "candles", label: "Kerzen" },
  { id: "bars", label: "Balken" },
];

export const baseOptions = (locked, intraday) => ({
  autoSize: true,
  localization: {
    locale: "de-DE",
    timeFormatter: (t) => (typeof t === "number"
      ? fmtTime(t, intraday ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "2-digit", year: "2-digit" })
      : String(t)),
  },
  layout: { background: { color: COLORS.bg }, textColor: COLORS.text, fontFamily: "Barlow, system-ui, sans-serif" },
  grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
  rightPriceScale: { borderColor: COLORS.line },
  timeScale: { borderColor: COLORS.line, timeVisible: true, secondsVisible: false, tickMarkFormatter: tickFormatter },
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

const shortDate = (iso) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y.slice(2)}`; };

/** Sperre gegen versehentliches Verschieben beim Scrollen der Seite (v. a. am Handy). */
export function LockButton({ locked, onToggle }) {
  const fine = finePointer();
  const lockedText = fine ? "Mausrad-Zoom einschalten" : "Zum Verschieben entsperren";
  return (
    <button type="button" className={`chart-lock ${locked ? "" : "open"}`} onClick={onToggle}
      aria-pressed={!locked} title={locked ? (fine ? "Ziehen und Achsen-Zoom gehen auch so; hiermit zoomt zusätzlich das Mausrad" : "Chart entsperren, um zu verschieben und zu zoomen") : "Chart wieder sperren"}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        {locked ? <path d="M7 11 V8 A5 5 0 0 1 17 8 V11 M5 11 H19 V21 H5 Z" /> : <path d="M7 11 V8 A5 5 0 0 1 16.5 6 M5 11 H19 V21 H5 Z" />}
      </svg>
      {locked ? lockedText : fine ? "Mausrad-Zoom aus" : "Sperren"}
    </button>
  );
}

/**
 * Kurschart. Einfach: Fläche des Schlusskurses. Profi: Kerzen mit Volumen, Durchschnitten, Bollinger, darunter RSI
 * und MACD. Overlays: Signal-Marker, Linien des Einstiegsplans und eigene Käufe mit Gewinn-/Verlustzone.
 * Standardmäßig gesperrt, damit Wischen die Seite scrollt und nicht den Chart verschiebt.
 */
export default function PriceChart({ rows, simple = false, type, live = null, intraday = false, showSma = true, showBb = false, events = [], planLines = [], positions = [], currency = null }) {
  const boxesRef = useRef([]);
  const kind = type || (simple ? "area" : "candles");
  const seriesRef = useRef(null);
  const dataRef = useRef({ data: [], last: -1, ohlc: false });
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
    const opts = baseOptions(lockedRef.current, intraday);
    const main = createChart(mainRef.current, opts);
    let priceSeries;
    const ohlc = kind === "candles" || kind === "bars";
    const up = rows[rows.length - 1].close >= rows[0].close;
    if (kind === "area") {
      priceSeries = main.addAreaSeries({
        lineColor: up ? COLORS.up : COLORS.down, lineWidth: 2,
        topColor: up ? "rgba(111, 211, 195, 0.28)" : "rgba(255, 107, 107, 0.25)", bottomColor: "rgba(17, 27, 38, 0)",
        priceLineVisible: true, priceLineColor: "#5d7389",
      });
    } else if (kind === "line") {
      priceSeries = main.addLineSeries({ color: up ? COLORS.up : COLORS.down, lineWidth: 2, priceLineVisible: true, priceLineColor: "#5d7389" });
    } else if (kind === "bars") {
      priceSeries = main.addBarSeries({ upColor: COLORS.up, downColor: COLORS.down, thinBars: rows.length > 120 });
    } else {
      priceSeries = main.addCandlestickSeries({
        upColor: COLORS.up, downColor: COLORS.down, borderVisible: false, wickUpColor: COLORS.up, wickDownColor: COLORS.down,
      });
    }
    const toPoint = (r) => (ohlc ? { time: r.time, open: r.open, high: r.high, low: r.low, close: r.close } : { time: r.time, value: r.close });
    priceSeries.setData(rows.map(toPoint));
    seriesRef.current = priceSeries;
    dataRef.current = { data: rows.map(toPoint), last: rows.length - 1, ohlc };
    if (!simple) {
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

    // Eigene Käufe wie beim Positions-Werkzeug von TradingView: ab dem Kaufzeitpunkt grüne Box bis zum Ziel, rote bis
    // zum Stopp, dazu der aktuelle Gewinn/Verlust als kräftige Fläche zwischen Kaufkurs und aktuellem Kurs.
    const markers = [];
    const open = positions.filter((p) => !p.sell_date);
    // Leere Zeitpunkte nach rechts, damit die Box offener Positionen auch bei einem Kauf von heute Platz hat
    let future = [];
    if (open.length && rows.length > 1) {
      const step = rows[rows.length - 1].time - rows[rows.length - 2].time;
      const n = Math.max(12, Math.round(Math.min(rows.length, 160) * 0.15));
      future = Array.from({ length: n }, (_, i) => rows[rows.length - 1].time + step * (i + 1));
      const data = [...rows.map(toPoint), ...future.map((time) => ({ time }))];
      priceSeries.setData(data);
      dataRef.current = { data, last: rows.length - 1, ohlc };
    }
    const times = rows.map((r) => r.time);
    const lastClose = rows[rows.length - 1].close;
    const boxes = [];
    const labelGroup = { taken: [], ts: 0 }; // Beschriftungen aller Positionen weichen einander aus
    positions.forEach((p) => {
      if (!p.buy_price) return;
      const start = buyTimestamp(p);
      const end = sellTimestamp(p);
      if (start > times[times.length - 1] + 86400 * 3 || (end && end < times[0])) return; // außerhalb des Zeitraums
      const box = new PositionBox({
        group: labelGroup, times, start, end, entry: p.buy_price, stop: end ? null : p.stop, target: end ? null : p.target,
        price: end ? p.sell_price : lastClose, qty: p.quantity, fees: p.fees || 0,
        fmt: (v, signed) => (signed ? signedMoney(v, currency) : money(v, currency)), fmtPct: (v) => pct(v, 1),
        label: `Kauf ${p.quantity}× ${money(p.buy_price, currency)} · ${shortDate(p.buy_date)}${p.buy_time ? ` ${p.buy_time}` : ""}`,
        short: `Kauf ${money(p.buy_price, currency)}`,
      });
      priceSeries.attachPrimitive(box);
      if (!end) boxes.push(box);
      // Achsenbeschriftungen ohne Linie (die Box zeigt die Bereiche)
      priceSeries.createPriceLine({ price: p.buy_price, color: COLORS.amber, lineVisible: false, axisLabelVisible: true, title: "" });
      if (!end && p.stop) priceSeries.createPriceLine({ price: p.stop, color: COLORS.down, lineVisible: false, axisLabelVisible: true, title: "" });
      if (!end && p.target) priceSeries.createPriceLine({ price: p.target, color: COLORS.up, lineVisible: false, axisLabelVisible: true, title: "" });
      const i0 = barIndex(times, start);
      if (i0 >= 0) markers.push({ time: times[i0], position: "belowBar", color: COLORS.amber, shape: "arrowUp", text: "Kauf", size: 2 });
      if (end) {
        const i1 = barIndex(times, end);
        if (i1 >= 0) markers.push({ time: times[i1], position: "aboveBar", color: COLORS.amber, shape: "arrowDown", text: "Verkauf", size: 2 });
      }
    });
    boxesRef.current = boxes;
    const hasPositions = markers.length > 0;

    // Vergangene Entscheidungspunkte: nur die jüngsten, damit der Chart ruhig bleibt; bei eigenen Käufen noch weniger
    const recent = events.slice(-(hasPositions ? 4 : simple ? 6 : 10));
    const labelFrom = simple ? Infinity : recent.length - 3;
    recent.forEach((e, i) => {
      const t = snap(rows, e.time);
      if (t === null || t - e.time > 7 * 86400) return;
      const text = i >= labelFrom ? e.label : "";
      markers.push(e.side === "buy"
        ? { time: t, position: "belowBar", color: COLORS.buySig, shape: "arrowUp", text, size: 1.5 }
        : { time: t, position: "aboveBar", color: COLORS.sellSig, shape: "arrowDown", text, size: 1.5 });
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
      main.timeScale().setVisibleLogicalRange({ from: rows.length - visible, to: rows.length + (future.length || 3) });
    }

    return () => { charts.forEach((c) => c.remove()); chartsRef.current = []; seriesRef.current = null; };
  }, [rows, simple, kind, intraday, showSma, showBb, events, planLines, positions, currency]);

  // Live-Kurs: letzte Kerze bzw. letzten Punkt aktualisieren, ohne den Chart neu aufzubauen
  useEffect(() => {
    const s = seriesRef.current;
    const { data, last, ohlc } = dataRef.current;
    if (!s || !live?.price || last < 0 || !data[last]) return;
    const cur = data[last];
    const next = ohlc
      ? { ...cur, close: live.price, high: Math.max(cur.high, live.price), low: Math.min(cur.low, live.price) }
      : { ...cur, value: live.price };
    if ((ohlc ? cur.close : cur.value) === live.price) return;
    data[last] = next;
    try { s.setData(data); } catch { /* Chart wurde gerade ersetzt */ }
    boxesRef.current.forEach((b) => b.update({ price: live.price }));
  }, [live]);

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
