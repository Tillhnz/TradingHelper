import { useEffect, useRef } from "react";
import { createChart, LineStyle } from "lightweight-charts";
import { bollinger, ema, indicatorTitle, INDICATORS, macd, rsi, sma } from "../indicators.js";
import { money, pct, signedMoney } from "../fmt.js";
import { buyTimestamp, PositionBox, sellTimestamp } from "./positionBox.js";
import { baseOptions, COLORS } from "./PriceChart.jsx";

/**
 * Verschieben/Zoomen. Senkrechtes Wischen bleibt beim Seiten-Scrollen (sonst „klebt“ die Seite am Chart);
 * mit aktivem Zeichenwerkzeug gehört jede Berührung dem Zeichnen.
 */
const pan = (on) => ({
  handleScroll: on ? { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false } : false,
  handleScale: on ? { mouseWheel: true, pinch: true, axisPressedMouseMove: true, axisDoubleClickReset: true } : false,
  kineticScroll: { touch: on, mouse: false },
});

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

const fmtPct = (x) => `${(x * 100).toFixed(1).replace(".", ",").replace(",0", "")} %`;

/** Daten einer Linie mit Lücken als „whitespace“, damit alle Fenster dieselben Zeitpunkte haben (Synchronisierung). */
const series = (rows, values) => rows.map((r, i) => (values[i] === null || values[i] === undefined
  ? { time: r.time } : { time: r.time, value: values[i] }));

/**
 * Freier Chart mit Zeichnungen und Kennlinien.
 * - tool: null | "hline" | "trend" | "ray" | "fib" – Tippen/Klicken oder Ziehen im Chart zeichnet
 * - onDraw(kind, points, { touch }) bei einer fertigen Zeichnung
 * - onPending(point) nach dem ersten Punkt einer Zwei-Punkt-Zeichnung (nur angetippt)
 * - pending: dieser erste Punkt (wird als Markierung gezeigt)
 * - magnet: Punkte rasten an Eröffnung/Hoch/Tief/Schluss der Kerze ein
 */
export default function WorkspaceChart({ rows, type = "candles", intraday = false, indicators = [], drawings = [],
  tool = null, pending = null, selected = null, onPending, onDraw, magnet = true, positions = [], currency = null }) {
  const mainRef = useRef(null);
  const subRefs = useRef({});
  const state = useRef({ charts: [], main: null, price: null, range: null });
  const toolRef = useRef(tool);
  const pendingRef = useRef(pending);
  const magnetRef = useRef(magnet);
  const drawRef = useRef(onDraw);
  const pendRef = useRef(onPending);
  toolRef.current = tool;
  pendingRef.current = pending;
  magnetRef.current = magnet;
  drawRef.current = onDraw;
  pendRef.current = onPending;

  const subs = indicators.filter((i) => INDICATORS[i.kind]?.pane === "sub");

  // Grundgerüst: Kurse, Kennlinien, Unterfenster. Zeichnungen kommen im zweiten Effekt dazu.
  useEffect(() => {
    if (!rows?.length || !mainRef.current) return undefined;
    const closes = rows.map((r) => r.close);
    const opts = { ...baseOptions(false, intraday), ...pan(!toolRef.current) };
    const main = createChart(mainRef.current, opts);
    const ohlc = type === "candles" || type === "bars";
    let price;
    if (type === "candles") {
      price = main.addCandlestickSeries({ upColor: COLORS.up, downColor: COLORS.down, borderVisible: false,
        wickUpColor: COLORS.up, wickDownColor: COLORS.down });
    } else if (type === "bars") {
      price = main.addBarSeries({ upColor: COLORS.up, downColor: COLORS.down, thinBars: rows.length > 150 });
    } else if (type === "line") {
      price = main.addLineSeries({ color: COLORS.up, lineWidth: 2 });
    } else {
      price = main.addAreaSeries({ lineColor: COLORS.up, lineWidth: 2, topColor: "rgba(111, 211, 195, 0.25)",
        bottomColor: "rgba(17, 27, 38, 0)" });
    }
    price.setData(rows.map((r) => (ohlc ? { time: r.time, open: r.open, high: r.high, low: r.low, close: r.close }
      : { time: r.time, value: r.close })));

    // Eigene Käufe als Positions-Box (Ziel grün, Stopp rot, aktueller Gewinn/Verlust)
    const times = rows.map((r) => r.time);
    const labelGroup = { taken: [], ts: 0 }; // Beschriftungen aller Positionen weichen einander aus
    for (const p of positions) {
      if (!p.buy_price) continue;
      const end = sellTimestamp(p);
      price.attachPrimitive(new PositionBox({
        group: labelGroup, times, start: buyTimestamp(p), end, entry: p.buy_price, stop: end ? null : p.stop, target: end ? null : p.target,
        price: end ? p.sell_price : rows[rows.length - 1].close, qty: p.quantity, fees: p.fees || 0,
        fmt: (v, signed) => (signed ? signedMoney(v, currency) : money(v, currency)), fmtPct: (v) => pct(v, 1),
        label: `Kauf ${p.quantity}× ${money(p.buy_price, currency)}`,
        short: `Kauf ${money(p.buy_price, currency)}`,
      }));
      // Werte an der Preisachse statt großer Beschriftungen im Chart
      price.createPriceLine({ price: p.buy_price, color: COLORS.amber, lineVisible: false, axisLabelVisible: true, title: "" });
      if (!end && p.stop) price.createPriceLine({ price: p.stop, color: COLORS.down, lineVisible: false, axisLabelVisible: true, title: "" });
      if (!end && p.target) price.createPriceLine({ price: p.target, color: COLORS.up, lineVisible: false, axisLabelVisible: true, title: "" });
    }

    const charts = [main];
    for (const ind of indicators) {
      const p = ind.params || {};
      const thin = { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
      if (ind.kind === "sma" || ind.kind === "ema") {
        const n = Math.max(1, Math.round(p.period || 20));
        // Name steht in der Legende oben links – nicht als Etikett im Chart
        const s = main.addLineSeries({ ...thin, color: ind.color, lineWidth: 2 });
        s.setData(series(rows, (ind.kind === "sma" ? sma : ema)(closes, n)));
      } else if (ind.kind === "bb") {
        const b = bollinger(closes, Math.max(2, Math.round(p.period || 20)), p.mult || 2);
        for (const [key, style] of [["upper", LineStyle.Solid], ["mid", LineStyle.Dotted], ["lower", LineStyle.Solid]]) {
          const s = main.addLineSeries({ ...thin, color: ind.color, lineWidth: 1, lineStyle: style });
          s.setData(series(rows, b[key]));
        }
      } else if (ind.kind === "volume" && rows.some((r) => r.volume)) {
        const v = main.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, ...thin });
        main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
        v.setData(rows.map((r) => ({ time: r.time, value: r.volume || 0,
          color: r.close >= r.open ? "rgba(111, 211, 195, 0.35)" : "rgba(255, 107, 107, 0.35)" })));
      }
    }
    for (const ind of indicators.filter((i) => INDICATORS[i.kind]?.pane === "sub")) {
      const el = subRefs.current[ind.id];
      if (!el) continue;
      const c = createChart(el, { ...opts, timeScale: { ...opts.timeScale, visible: false } });
      const p = ind.params || {};
      const thin = { priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false };
      if (ind.kind === "rsi") {
        const s = c.addLineSeries({ ...thin, color: ind.color, lineWidth: 2, title: indicatorTitle(ind) });
        s.setData(series(rows, rsi(closes, Math.max(2, Math.round(p.period || 14)))));
        for (const [lvl, col] of [[70, COLORS.down], [30, COLORS.up]]) {
          s.createPriceLine({ price: lvl, color: col, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
        }
      } else if (ind.kind === "macd") {
        const m = macd(closes, p.fast || 12, p.slow || 26, p.signal || 9);
        const h = c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
        h.setData(rows.map((r, i) => (m.hist[i] === null ? { time: r.time }
          : { time: r.time, value: m.hist[i], color: m.hist[i] >= 0 ? "rgba(111, 211, 195, 0.5)" : "rgba(255, 107, 107, 0.5)" })));
        c.addLineSeries({ ...thin, color: ind.color, lineWidth: 2, title: indicatorTitle(ind) }).setData(series(rows, m.line));
        c.addLineSeries({ ...thin, color: COLORS.signal, lineWidth: 1, lastValueVisible: false }).setData(series(rows, m.signal));
      }
      charts.push(c);
    }

    let syncing = false;
    charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range || syncing) return;
      syncing = true;
      charts.forEach((o) => { if (o !== c) o.timeScale().setVisibleLogicalRange(range); });
      syncing = false;
      if (c === main) state.current.range = range;
    }));
    // Startansicht: alle Kurse; die Unterfenster folgen dem Hauptchart
    // Mit offener Position etwas Platz rechts lassen: dort stehen Ziel und Stopp, ohne die letzten Kerzen zu verdecken
    if (positions.some((p) => p.buy_price && !p.sell_date)) {
      main.timeScale().applyOptions({ rightOffset: Math.max(4, Math.round(rows.length * 0.12)) });
    }
    if (state.current.range) main.timeScale().setVisibleLogicalRange(state.current.range);
    else main.timeScale().fitContent();
    const r0 = main.timeScale().getVisibleLogicalRange();
    if (r0) charts.slice(1).forEach((c) => c.timeScale().setVisibleLogicalRange(r0));

    // Zeichnen per Pointer-Ereignis (Maus, Finger, Stift):
    // - Tippen/Klicken setzt einen Punkt, bei Zwei-Punkt-Werkzeugen danach den zweiten
    // - Ziehen zeichnet in einem Zug (Anfang beim Aufsetzen, Ende beim Loslassen) – auf dem Handy der bequeme Weg
    // - währenddessen zeigt eine gestrichelte Vorschau samt Preis an der Achse, wo die Linie landet
    // - Magnet: der Punkt rastet an Eröffnung/Hoch/Tief/Schluss der Kerze ein, wenn er nah dran ist
    const el = mainRef.current;
    let preview = null;
    const clearPreview = () => {
      if (!preview) return;
      if (preview.series) { try { main.removeSeries(preview.series); } catch { /* schon weg */ } }
      if (preview.line) { try { price.removePriceLine(preview.line); } catch { /* schon weg */ } }
      preview = null;
    };
    const showPreview = (kind, a, b) => {
      if (!preview) preview = {};
      const at = b || a;
      if (!preview.line) {
        preview.line = price.createPriceLine({ price: at.price, color: "#ffffff", lineWidth: 1, lineStyle: LineStyle.Dashed,
          axisLabelVisible: true, title: "" });
      } else preview.line.applyOptions({ price: at.price });
      if (kind === "hline" || !b) return;
      if (!preview.series) {
        preview.series = main.addLineSeries({ color: "#ffffff", lineWidth: 2, lineStyle: LineStyle.Dashed, priceLineVisible: false,
          lastValueVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null });
      }
      const [p1, p2] = a.time <= b.time ? [a, b] : [b, a];
      preview.series.setData(p1.time === p2.time ? [] : [{ time: p1.time, value: p1.price }, { time: p2.time, value: p2.price }]);
    };
    const pointAt = (clientX, clientY, coarse) => {
      const rect = el.getBoundingClientRect();
      const x = clientX - rect.left, y = clientY - rect.top;
      const ts = main.timeScale();
      if (x < 0 || y < 0 || x > ts.width() || y > rect.height - ts.height()) return null;
      const lg = ts.coordinateToLogical(x);
      const p = price.coordinateToPrice(y);
      if (lg === null || p === null) return null;
      const raw = Math.round(lg);
      const i = Math.max(0, Math.min(rows.length - 1, raw));
      const bar = rows[i];
      let value = p;
      if (magnetRef.current && raw === i) {
        let best = null, dist = Infinity;
        for (const v of ohlc ? [bar.open, bar.high, bar.low, bar.close] : [bar.close]) {
          if (v === null || v === undefined) continue;
          const cy = price.priceToCoordinate(v);
          if (cy === null) continue;
          if (Math.abs(cy - y) < dist) { dist = Math.abs(cy - y); best = v; }
        }
        if (best !== null && dist <= (coarse ? 28 : 14)) value = best;
      }
      return { time: bar.time, price: value };
    };

    let gesture = null;
    const onDown = (e) => {
      const tool = toolRef.current;
      if (!tool || (e.pointerType === "mouse" && e.button !== 0)) return;
      const coarse = e.pointerType !== "mouse";
      const pt = pointAt(e.clientX, e.clientY, coarse);
      if (!pt) return;
      e.preventDefault();
      e.stopPropagation();
      try { el.setPointerCapture(e.pointerId); } catch { /* egal */ }
      const pending = pendingRef.current;
      gesture = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false, coarse, last: pt,
        anchor: tool === "hline" ? null : (pending || pt), hadPending: !!pending };
      if (tool === "hline") showPreview("hline", pt);
      else showPreview(tool, gesture.anchor, pending ? pt : null);
    };
    const onMove = (e) => {
      const tool = toolRef.current;
      if (!tool) return;
      if (gesture && e.pointerId === gesture.id) {
        e.preventDefault();
        if (Math.hypot(e.clientX - gesture.x, e.clientY - gesture.y) > 8) gesture.moved = true;
        const pt = pointAt(e.clientX, e.clientY, gesture.coarse);
        if (!pt) return;
        gesture.last = pt;
        if (tool === "hline") showPreview("hline", pt);
        else if (gesture.moved || gesture.hadPending) showPreview(tool, gesture.anchor, pt);
        return;
      }
      // Maus ohne gedrückte Taste: Vorschau vom ersten Punkt bis zum Zeiger
      if (e.pointerType === "mouse" && pendingRef.current && tool !== "hline") {
        const pt = pointAt(e.clientX, e.clientY, false);
        if (pt) showPreview(tool, pendingRef.current, pt);
      }
    };
    const onUp = (e) => {
      if (!gesture || e.pointerId !== gesture.id) return;
      const g = gesture;
      gesture = null;
      const tool = toolRef.current;
      const pt = pointAt(e.clientX, e.clientY, g.coarse) || g.last;
      clearPreview();
      if (!tool) return;
      const info = { touch: g.coarse };
      if (tool === "hline") { drawRef.current?.("hline", [pt], info); return; }
      const sameBar = pt.time === g.anchor.time;
      if ((g.moved || g.hadPending) && !(sameBar && tool !== "fib")) {
        drawRef.current?.(tool, [g.anchor, pt], info);
        return;
      }
      // Nur angetippt (oder senkrecht auf derselben Kerze gezogen): das ist der erste Punkt
      if (!g.hadPending) pendRef.current?.(g.moved ? pt : g.anchor);
    };
    const onCancel = () => { gesture = null; clearPreview(); };
    const onLeave = (e) => { if (e.pointerType === "mouse" && !gesture) clearPreview(); };
    const cap = { capture: true, passive: false };
    el.addEventListener("pointerdown", onDown, cap);
    el.addEventListener("pointermove", onMove, cap);
    el.addEventListener("pointerup", onUp, cap);
    el.addEventListener("pointercancel", onCancel, cap);
    el.addEventListener("pointerleave", onLeave);

    state.current = { ...state.current, charts, main, price, lastTime: rows[rows.length - 1].time, clearPreview };
    return () => {
      el.removeEventListener("pointerdown", onDown, cap);
      el.removeEventListener("pointermove", onMove, cap);
      el.removeEventListener("pointerup", onUp, cap);
      el.removeEventListener("pointercancel", onCancel, cap);
      el.removeEventListener("pointerleave", onLeave);
      charts.forEach((c) => c.remove());
      state.current = { ...state.current, charts: [], main: null, price: null, clearPreview: null };
    };
  }, [rows, type, intraday, indicators, positions, currency]); // eslint-disable-line react-hooks/exhaustive-deps

  // Werkzeug gewechselt: Verschieben an/aus, offene Vorschau weg
  useEffect(() => {
    state.current.charts.forEach((c) => c.applyOptions(pan(!tool)));
    state.current.clearPreview?.();
  }, [tool, pending]);

  // Zeichnungen: eigene Serien/Linien, werden bei jeder Änderung neu gesetzt
  useEffect(() => {
    const { main, price, lastTime } = state.current;
    if (!main || !price) return undefined;
    const lines = [], extra = [];
    const addLine = (opts) => { lines.push(price.createPriceLine(opts)); };
    for (const d of drawings) {
      const width = d.id === selected ? 3 : 2;
      const [a, b] = d.points;
      if (d.kind === "hline") {
        addLine({ price: a.price, color: d.color, lineWidth: width, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: d.label || "" });
      } else if ((d.kind === "trend" || d.kind === "ray") && b) {
        const [p1, p2] = a.time <= b.time ? [a, b] : [b, a];
        if (p1.time === p2.time) continue;
        let end = p2;
        if (d.kind === "ray" && lastTime > p2.time) {
          const slope = (p2.price - p1.price) / (p2.time - p1.time);
          end = { time: lastTime, price: p2.price + slope * (lastTime - p2.time) };
        }
        const s = main.addLineSeries({ color: d.color, lineWidth: width, priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false, autoscaleInfoProvider: () => null, title: d.label || "" });
        s.setData([{ time: p1.time, value: p1.price }, { time: end.time, value: end.price }]);
        extra.push(s);
      } else if (d.kind === "fib" && b) {
        const hi = b.price, lo = a.price;
        for (const lvl of FIB_LEVELS) {
          addLine({ price: hi - (hi - lo) * lvl, color: d.color, lineWidth: lvl === 0.5 || lvl === 0.618 ? width : 1,
            lineStyle: lvl === 0 || lvl === 1 ? LineStyle.Solid : LineStyle.Dashed, axisLabelVisible: true,
            title: `${d.label ? `${d.label} ` : ""}${fmtPct(lvl)}` });
        }
      }
    }
    if (pending) {
      addLine({ price: pending.price, color: "#ffffff", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: true, title: "Punkt 1" });
    }
    return () => {
      if (state.current.price !== price) return; // Chart wurde schon neu gebaut
      lines.forEach((l) => { try { price.removePriceLine(l); } catch { /* schon weg */ } });
      extra.forEach((s) => { try { main.removeSeries(s); } catch { /* schon weg */ } });
    };
  }, [drawings, pending, selected, rows, type, intraday, indicators]);

  return (
    <div className={`ws-chart ${tool ? "drawing" : ""}`}>
      <div className="ws-main-wrap">
        <div className="ws-main" ref={mainRef} />
        {indicators.some((i) => INDICATORS[i.kind]?.pane !== "sub") && (
          <div className="chart-legend" aria-label="Kennlinien">
            {indicators.filter((i) => INDICATORS[i.kind]?.pane !== "sub").map((i) => (
              <span key={i.id}><i style={{ background: i.color }} />{indicatorTitle(i)}</span>
            ))}
          </div>
        )}
      </div>
      {subs.map((s) => (
        <div key={s.id} className="ws-sub">
          <span className="ws-sub-label">{indicatorTitle(s)}</span>
          <div className="ws-sub-chart" ref={(el) => { subRefs.current[s.id] = el; }} />
        </div>
      ))}
    </div>
  );
}
