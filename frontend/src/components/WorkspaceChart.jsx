import { useEffect, useRef } from "react";
import { createChart, LineStyle } from "lightweight-charts";
import { bollinger, ema, indicatorTitle, INDICATORS, macd, rsi, sma } from "../indicators.js";
import { money, pct, signedMoney } from "../fmt.js";
import { buyTimestamp, PositionBox, sellTimestamp } from "./positionBox.js";
import { baseOptions, COLORS } from "./PriceChart.jsx";

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

const fmtPct = (x) => `${(x * 100).toFixed(1).replace(".", ",").replace(",0", "")} %`;

/** Daten einer Linie mit Lücken als „whitespace“, damit alle Fenster dieselben Zeitpunkte haben (Synchronisierung). */
const series = (rows, values) => rows.map((r, i) => (values[i] === null || values[i] === undefined
  ? { time: r.time } : { time: r.time, value: values[i] }));

/**
 * Freier Chart mit Zeichnungen und Kennlinien.
 * - tool: null | "hline" | "trend" | "ray" | "fib" – Klicks in den Chart setzen Punkte
 * - onPoint({time, price}) wird bei jedem Klick mit aktivem Werkzeug aufgerufen
 * - pending: erster Punkt einer Zwei-Punkt-Zeichnung (wird als Markierung gezeigt)
 */
export default function WorkspaceChart({ rows, type = "candles", intraday = false, indicators = [], drawings = [],
  tool = null, pending = null, selected = null, onPoint, positions = [], currency = null }) {
  const mainRef = useRef(null);
  const subRefs = useRef({});
  const state = useRef({ charts: [], main: null, price: null, range: null });
  const toolRef = useRef(tool);
  const pointRef = useRef(onPoint);
  toolRef.current = tool;
  pointRef.current = onPoint;

  const subs = indicators.filter((i) => INDICATORS[i.kind]?.pane === "sub");

  // Grundgerüst: Kurse, Kennlinien, Unterfenster. Zeichnungen kommen im zweiten Effekt dazu.
  useEffect(() => {
    if (!rows?.length || !mainRef.current) return undefined;
    const closes = rows.map((r) => r.close);
    const opts = { ...baseOptions(false, intraday), handleScroll: true, handleScale: true };
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

    // Klicks direkt am Element auswerten: die Klick-Ereignisse der Chart-Bibliothek verschlucken einen zweiten
    // schnellen Klick (Doppelklick-Erkennung), für Zwei-Punkt-Zeichnungen braucht es aber jeden Klick
    const el = mainRef.current;
    const onClick = (e) => {
      if (!toolRef.current) return;
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      if (x < 0 || y < 0 || x > main.timeScale().width() || y > rect.height - main.timeScale().height()) return;
      const p = price.coordinateToPrice(y);
      let t = main.timeScale().coordinateToTime(x);
      if (t === null || t === undefined) {
        // Rechts neben den Kursen: an den letzten Kurs anhängen
        const lg = main.timeScale().coordinateToLogical(x);
        if (lg !== null && lg > rows.length - 1) t = rows[rows.length - 1].time;
      }
      if (p === null || t === null || t === undefined) return;
      pointRef.current?.({ time: typeof t === "number" ? t : Math.floor(new Date(`${t.year}-${t.month}-${t.day}`).getTime() / 1000), price: p });
    };
    el.addEventListener("click", onClick);

    state.current = { ...state.current, charts, main, price, lastTime: rows[rows.length - 1].time };
    return () => { el.removeEventListener("click", onClick); charts.forEach((c) => c.remove()); state.current = { ...state.current, charts: [], main: null, price: null }; };
  }, [rows, type, intraday, indicators, positions, currency]); // eslint-disable-line react-hooks/exhaustive-deps

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
