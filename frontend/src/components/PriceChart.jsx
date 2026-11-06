import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode, LineStyle } from "lightweight-charts";

export const COLORS = {
  bg: "#111b26", text: "#8d9eb0", grid: "#1a2735", line: "#263749",
  up: "#6fd3c3", down: "#ff6b6b", amber: "#f2b84b",
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

const dayStart = (iso) => Math.floor(new Date(`${iso}T00:00:00Z`).getTime() / 1000);
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
export default function PriceChart({ rows, simple = false, type, live = null, intraday = false, showSma = true, showBb = false, events = [], planLines = [], positions = [] }) {
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

    // Eigene Käufe wie beim Positions-Werkzeug von TradingView: rote Fläche Kauf → Stopp, grüne Fläche Kauf → Ziel,
    // dazu die Kurslinie ab Kauf grün über bzw. rot unter dem Kaufkurs.
    const markers = [];
    const open = positions.filter((p) => !p.sell_date);
    // Leere Zeitpunkte nach rechts, damit die Zonen offener Positionen auch bei einem Kauf von heute sichtbar sind
    let future = [];
    if (open.length && rows.length > 1 && !intraday) {
      const step = rows[rows.length - 1].time - rows[rows.length - 2].time;
      // etwa ein Siebtel der sichtbaren Breite, damit die Zonen klar zu sehen sind
      const n = Math.max(12, Math.round(Math.min(rows.length, 160) * 0.15));
      future = Array.from({ length: n }, (_, i) => rows[rows.length - 1].time + step * (i + 1));
      const data = [...rows.map(toPoint), ...future.map((time) => ({ time }))];
      priceSeries.setData(data);
      dataRef.current = { data, last: rows.length - 1, ohlc };
    }
    positions.forEach((p) => {
      // Im Tagesverlauf nur Linien: Zonen und Kaufpfeile alter Käufe würden die Skala sprengen
      if (intraday) {
        if (p.sell_date) return;
        priceSeries.createPriceLine({ price: p.buy_price, color: COLORS.amber, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: `Kauf ${shortDate(p.buy_date)}` });
        if (p.stop) priceSeries.createPriceLine({ price: p.stop, color: COLORS.down, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "Stopp" });
        if (p.target) priceSeries.createPriceLine({ price: p.target, color: COLORS.up, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "Ziel" });
        return;
      }
      // Tageskerzen liegen je nach Börse auf Mitternacht Ortszeit (gettex: 23 Uhr UTC am Vortag), daher ±12 h Spielraum
      const from = dayStart(p.buy_date) - 12 * 3600;
      const to = p.sell_date ? dayStart(p.sell_date) + 12 * 3600 : Infinity;
      let seg = rows.filter((r) => r.time >= from && r.time <= to);
      if (!seg.length && !p.sell_date && rows.length) seg = rows.slice(-1); // Kauf nach der letzten Kerze
      if (!seg.length || !p.buy_price) return;
      const band = (level, color) => {
        const s2 = main.addBaselineSeries({
          baseValue: { type: "price", price: p.buy_price },
          topLineColor: "rgba(0,0,0,0)", bottomLineColor: "rgba(0,0,0,0)", lineWidth: 1,
          topFillColor1: color, topFillColor2: color, bottomFillColor1: color, bottomFillColor2: color,
          priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
        });
        s2.setData([...seg.map((r) => r.time), ...future].map((time) => ({ time, value: level })));
      };
      if (!p.sell_date && p.stop) band(p.stop, "rgba(255, 107, 107, 0.22)");
      if (!p.sell_date && p.target) band(p.target, "rgba(111, 211, 195, 0.20)");
      const area = main.addBaselineSeries({
        baseValue: { type: "price", price: p.buy_price },
        topLineColor: COLORS.up, topFillColor1: "rgba(111, 211, 195, 0.30)", topFillColor2: "rgba(111, 211, 195, 0.05)",
        bottomLineColor: COLORS.down, bottomFillColor1: "rgba(255, 107, 107, 0.05)", bottomFillColor2: "rgba(255, 107, 107, 0.30)",
        lineWidth: 3, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
      });
      area.setData(seg.map((r) => ({ time: r.time, value: r.close })));
      area.createPriceLine({ price: p.buy_price, color: COLORS.amber, lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: `Kauf ${p.quantity}× · ${shortDate(p.buy_date)}` });
      if (!p.sell_date) {
        if (p.stop) area.createPriceLine({ price: p.stop, color: COLORS.down, lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "Stopp" });
        if (p.target) area.createPriceLine({ price: p.target, color: COLORS.up, lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "Ziel" });
      }
      markers.push({ time: seg[0].time, position: "belowBar", color: COLORS.amber, shape: "arrowUp", text: `Kauf ${shortDate(p.buy_date)}`, size: 2 });
      if (p.sell_date) markers.push({ time: seg[seg.length - 1].time, position: "aboveBar", color: COLORS.amber, shape: "arrowDown", text: `Verkauf ${shortDate(p.sell_date)}`, size: 2 });
    });
    const hasPositions = markers.length > 0;

    // Vergangene Entscheidungspunkte: nur die jüngsten, damit der Chart ruhig bleibt; bei eigenen Käufen noch weniger
    const recent = events.slice(-(hasPositions ? 4 : simple ? 6 : 10));
    const labelFrom = simple ? Infinity : recent.length - 3;
    recent.forEach((e, i) => {
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
      main.timeScale().setVisibleLogicalRange({ from: rows.length - visible, to: rows.length + (future.length || 3) });
    }

    return () => { charts.forEach((c) => c.remove()); chartsRef.current = []; seriesRef.current = null; };
  }, [rows, simple, kind, intraday, showSma, showBb, events, planLines, positions]);

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
