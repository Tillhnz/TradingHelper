import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import BuyDialog from "../components/BuyDialog.jsx";
import EntryPlan from "../components/EntryPlan.jsx";
import HoldingPanel from "../components/HoldingPanel.jsx";
import SellDialog from "../components/SellDialog.jsx";
import NewsList from "../components/NewsList.jsx";
import PriceChart, { CHART_TYPES } from "../components/PriceChart.jsx";
import Term from "../components/Term.jsx";
import { ActionBadge, ErrorText, Levels, Loading, Stat } from "../components/ui.jsx";
import { CURRENCY_LABEL, money, num, pct, signed, tone } from "../fmt.js";
import { since, useLiveQuotes } from "../live.js";
import { useMode } from "../mode.js";
import { ACTION_UI, displayName, displayTicker } from "../texts.js";

const RANGES = [
  { id: "1d", label: "1 T", period: "1d", interval: "5m" },
  { id: "5d", label: "1 W", period: "5d", interval: "15m" },
  { id: "1mo", label: "1 M", period: "1mo", interval: "1d" },
  { id: "3mo", label: "3 M", period: "3mo", interval: "1d" },
  { id: "6mo", label: "6 M", period: "6mo", interval: "1d" },
  { id: "1y", label: "1 J", period: "1y", interval: "1d" },
  { id: "5y", label: "5 J", period: "5y", interval: "1wk" },
];
const PRO_PERIODS = {
  "1d": ["3mo", "6mo", "1y", "2y", "5y"],
  "1wk": ["1y", "2y", "5y", "10y"],
  "1h": ["5d", "1mo", "3mo", "6mo"],
  "15m": ["1d", "5d", "1mo"],
  "5m": ["1d", "5d"],
};
const INTRADAY = new Set(["1h", "15m", "5m"]);
const BAR_SECONDS = { "5m": 300, "15m": 900, "1h": 3600 };
const TYPE_KEY = "tradehelper_chart_type";
const loadType = () => { try { return localStorage.getItem(TYPE_KEY) || null; } catch { return null; } };
const LABEL = { "1d": "1 Tag", "5d": "5 Tage", "1mo": "1 Monat", "3mo": "3 Monate", "6mo": "6 Monate", "1y": "1 Jahr", "2y": "2 Jahre", "5y": "5 Jahre", "10y": "10 Jahre" };
const INTERVAL_LABEL = { "1d": "Tag", "1wk": "Woche", "1h": "Stunde", "15m": "15 Min", "5m": "5 Min" };
const REFRESH_MS = 60 * 1000;
const KIND_COLOR = { pullback: "#6fd3c3", breakout: "#f2b84b", rebound: "#ff9f6b", now: "#6fd3c3" };
const KIND_TITLE = { pullback: "Rücksetzer", breakout: "Ausbruch", rebound: "Rebound", now: "Einstieg" };

function freshness(meta) {
  if (!meta) return "";
  const when = meta.as_of ? new Date(meta.as_of * 1000).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : null;
  const delay = meta.delay_min === 0 ? "Echtzeit" : meta.delay_min ? `${meta.delay_min} Min. verzögert` : null;
  return [when && `Stand ${when}`, delay].filter(Boolean).join(" · ");
}

export default function ChartPage() {
  const { symbol: param } = useParams();
  const symbol = (param || "").toUpperCase();
  const { mode } = useMode();
  const pro = mode === "pro";
  const [view, setView] = useState({ period: "1y", interval: "1d" });
  const [showSma, setShowSma] = useState(true);
  const [showBb, setShowBb] = useState(false);
  const [showEvents, setShowEvents] = useState(true);
  const [showPlan, setShowPlan] = useState(true);
  const [planTouched, setPlanTouched] = useState(false);
  const [ccy, setCcy] = useState(null); // null = Einstellung
  const [meta, setMeta] = useState(null);
  const [rows, setRows] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [watched, setWatched] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [buying, setBuying] = useState(false);
  const [selling, setSelling] = useState(null);
  const [tick, setTick] = useState(0);
  const [chartType, setChartType] = useState(loadType);
  const [optsOpen, setOptsOpen] = useState(false);
  const [holding, setHolding] = useState(null);
  const refreshAll = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    setHolding(null);
    setMeta(null);
    api.get(`/holdings/${encodeURIComponent(symbol)}`).then((h) => {
      setHolding(h);
      if (!planTouched) setShowPlan(!(h?.summary?.shares > 0));
    }).catch(() => setHolding(null));
    api.get("/watchlist").then((w) => setWatched(w.some((x) => x.symbol === symbol))).catch(() => {});
  }, [symbol, tick]);

  const q = `period=${view.period}&interval=${view.interval}${ccy ? `&currency=${ccy}` : ""}`;
  useEffect(() => {
    let stop = false;
    setRows(null);
    setError("");
    api.get(`/history/${encodeURIComponent(symbol)}?${q}`)
      .then((r) => { if (!stop) { setRows(r.rows); setMeta(r); } })
      .catch((e) => { if (!stop) setError(e.message); });
    return () => { stop = true; };
  }, [symbol, q, tick]);

  // Einschätzung immer auf Tagesbasis über den Zeitraum der Strategie, damit sie zur Übersicht passt
  useEffect(() => {
    let stop = false;
    setAnalysis(null);
    api.get(`/analysis/${encodeURIComponent(symbol)}?interval=1d${ccy ? `&currency=${ccy}` : ""}`)
      .then((a) => { if (!stop) setAnalysis(a); })
      .catch(() => {});
    return () => { stop = true; };
  }, [symbol, ccy, tick]);

  // Kurse jede Minute still nachladen, solange die Seite sichtbar ist
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      api.get(`/history/${encodeURIComponent(symbol)}?${q}`).then((r) => { setRows(r.rows); setMeta(r); }).catch(() => {});
    }, INTRADAY.has(view.interval) ? REFRESH_MS : 5 * REFRESH_MS);
    return () => clearInterval(id);
  }, [symbol, q, view.interval]);

  useEffect(() => {
    const name = meta?.name || analysis?.name;
    if (name) document.title = `${name} · TradeHelper`;
  }, [meta, analysis]);

  const planLines = useMemo(() => {
    if (!analysis || !showPlan) return [];
    const lines = pro ? [
      { price: analysis.support, color: "rgba(111, 211, 195, 0.45)", title: "Unterstützung", style: 2 },
      { price: analysis.resistance, color: "rgba(255, 107, 107, 0.45)", title: "Widerstand", style: 2 },
    ] : [];
    if (!analysis.entry) return lines;
    const ok = analysis.entry.setups.filter((x) => x.ok);
    ok.forEach((x) => { if (x.kind !== "now") lines.push({ price: x.entry, color: KIND_COLOR[x.kind], title: KIND_TITLE[x.kind], width: 2, style: 0 }); });
    const best = ok.find((x) => x.status === "now") || [...ok].sort((a, b) => Math.abs(a.distance_pct) - Math.abs(b.distance_pct))[0];
    if (best && !(holding?.summary?.shares > 0)) {
      lines.push({ price: best.stop, color: "#ff6b6b", title: "Stopp", style: 3 });
      if (best.target) lines.push({ price: best.target, color: "#6fd3c3", title: "Ziel", style: 3 });
    }
    return lines;
  }, [analysis, showPlan, pro, holding]);

  const events = useMemo(() => (showEvents && meta?.events ? meta.events : []), [meta, showEvents]);
  const positions = useMemo(() => meta?.positions || [], [meta]);

  async function toggleWatch() {
    setMsg("");
    setError("");
    try {
      if (watched) await api.del(`/watchlist/${encodeURIComponent(symbol)}`);
      else await api.post("/watchlist", { symbol });
      setWatched(!watched);
      setMsg(watched ? "Wird nicht mehr beobachtet." : "Zu „Meine Werte“ hinzugefügt – ab morgen in deiner Zusammenfassung.");
    } catch (e) {
      setError(e.message);
    }
  }

  const limited = !!meta?.intraday_limit;
  const periodsFor = (iv) => PRO_PERIODS[iv].filter((x) => !limited || !INTRADAY.has(iv) || ["1d", "5d"].includes(x));

  function pickType(t) {
    setChartType(t);
    try { localStorage.setItem(TYPE_KEY, t); } catch { /* egal */ }
  }

  function setProInterval(iv) {
    const periods = periodsFor(iv);
    setView((v) => ({ interval: iv, period: periods.includes(v.period) ? v.period : periods[Math.min(1, periods.length - 1)] }));
  }

  const quotes = useLiveQuotes([symbol], { currency: ccy, every: 15000 });
  const m = analysis?.metrics || {};
  const rec = analysis?.recommendation;
  const cur = meta?.currency ?? analysis?.currency;
  const p = (v) => money(v, cur);
  const ccyValue = ccy || meta?.display_currency || "native";
  const held = holding?.summary?.shares > 0;
  const openBlocks = (holding?.items || []).filter((x) => !x.closed)
    .sort((a, b) => (a.buy_date + (a.buy_time || "")).localeCompare(b.buy_date + (b.buy_time || "")));
  const last = rows?.[rows.length - 1];
  const prevRow = rows?.[rows.length - 2];
  const lq = quotes[symbol];
  const quoteOk = lq && (!cur || lq.currency === cur);
  const livePrice = quoteOk ? lq.price : view.interval === "1d" && last ? last.close : analysis?.last_close;
  const liveChange = quoteOk && lq.change_pct != null ? lq.change_pct : view.interval === "1d" && last && prevRow ? (last.close / prevRow.close - 1) * 100 : analysis?.change_pct_1d;
  // Live-Kurs nur in die letzte Kerze schreiben, wenn sie zum selben Zeitraum gehört
  const liveBar = useMemo(() => {
    if (!quoteOk || !last || !lq.time) return null;
    if (INTRADAY.has(view.interval)) return lq.time - last.time < (BAR_SECONDS[view.interval] || 900) ? { price: lq.price } : null;
    if (view.interval === "1d") return new Date(lq.time * 1000).toDateString() === new Date(last.time * 1000).toDateString() ? { price: lq.price } : null;
    return null;
  }, [quoteOk, lq, last, view.interval]);
  const bestSetup = analysis?.entry?.setups?.find((x) => x.ok && x.status === "now") || analysis?.entry?.setups?.find((x) => x.ok);
  const info = meta || analysis;
  const ui = rec ? ACTION_UI[rec.action] : null;
  const rangeId = RANGES.find((r) => r.period === view.period && r.interval === view.interval)?.id;
  const intervals = ["5m", "15m", "1h", "1d", "1wk"].filter((iv) => meta?.intraday !== false || !INTRADAY.has(iv));
  const ranges = RANGES;

  return (
    <>
      <div className="stock-head">
        <div className="stock-id">
          <Link to="/watchlist" className="back-link small">← Meine Werte</Link>
          <h1>{info?.name || displayTicker({ symbol })}</h1>
          <p className="muted small">
            {displayTicker({ symbol, ticker: info?.ticker })}
            {info?.exchange && <> · {info.exchange === "gettex" ? <Term name="gettex" /> : info.exchange}</>}
            {info?.native_currency && ` · ${info.native_currency}`}
            {info?.isin && ` · ${info.isin}`}
          </p>
        </div>
        <div className="stock-quote">
          {livePrice != null && (
            <>
              <strong className="big-price">{p(livePrice)}</strong>
              <span className={`chip ${tone(liveChange)}`}>{pct(liveChange)} heute</span>
            </>
          )}
          {quoteOk && lq.time ? (
            <p className={`muted small ${lq.delay_min ? "delayed" : ""}`}>
              <Term name="Verzögerung">Letztes Geschäft {since(lq.time)}{lq.delay_min ? ` · ${lq.delay_min} Min. verzögert` : lq.delay_min === 0 ? " · Echtzeit" : ""}</Term>
              {lq.bid && lq.ask && <> · <Term name="Geld/Brief">Geld {p(lq.bid)} / Brief {p(lq.ask)}</Term></>}
              {meta?.native_currency && meta.currency !== meta.native_currency && ` · umgerechnet in ${meta.currency}`}
            </p>
          ) : meta && <p className={`muted small ${meta.delay_min ? "delayed" : ""}`}><Term name="Verzögerung">{freshness(meta)}</Term>{meta.native_currency && meta.currency !== meta.native_currency && ` · umgerechnet in ${meta.currency}`}</p>}
        </div>
        <div className="stock-actions-top">
          <button className="btn primary btn-buy" onClick={() => setBuying(true)} title="Kurs und Uhrzeit von jetzt übernehmen">{held ? "+ Nachkauf" : "Kauf"}</button>
          {held && <button className="btn btn-sell" onClick={() => setSelling({})} title="Kurs und Uhrzeit von jetzt übernehmen">Verkauf</button>}
          {watched !== null && !held && <button className="btn" onClick={toggleWatch}>{watched ? "✓ Beobachtet" : "☆ Beobachten"}</button>}
          <Link className="btn" to={`/alerts?symbol=${encodeURIComponent(symbol)}`}>🔔 Alarm</Link>
          <Link className="btn" to={`/charts/${encodeURIComponent(symbol)}`} title="Großer Chart: Linien und Kennlinien selbst einzeichnen">⛶ Großer Chart</Link>
        </div>
      </div>
      {msg && <p className="ok" role="status">{msg}</p>}

      <div className="stock-layout">
      <aside className="stock-side">
      {rec && (
        <section className={`verdict ${ui?.tone || ""}`}>
          <div className="verdict-main">
            <span className="verdict-label">{held ? "Für deinen Bestand" : "Unsere Einschätzung"}</span>
            <ActionBadge action={rec.action} held={held} large />
            <p className="verdict-text">{held && holding.summary.advice ? holding.summary.advice.text : ui?.explain}</p>
          </div>
          <ul className="verdict-reasons">
            {(pro ? rec.reasons : rec.reasons.slice(0, 2)).map((r) => <li key={r}>{r}</li>)}
          </ul>
          <p className="muted small verdict-foot">
            Passend zu deiner Strategie <Link to="/settings">{rec.profile}</Link>
            {pro && <> · <Term name="Score">Score</Term> {signed(rec.combined)}</>}
          </p>
        </section>
      )}

      <HoldingPanel holding={holding} onChanged={refreshAll} onBuyMore={() => setBuying(true)} onSell={(id) => setSelling({ id })} />
      </aside>

      <div className="stock-main">
      <section className="panel chart-panel">
        <div className={`toolbar ${optsOpen ? "opts-open" : ""}`}>
          {pro ? (
            <>
              <div className="seg" role="group" aria-label="Kerzen">
                {intervals.map((iv) => <button key={iv} className={iv === view.interval ? "on" : ""} onClick={() => setProInterval(iv)}>{INTERVAL_LABEL[iv]}</button>)}
              </div>
              <select value={view.period} onChange={(e) => setView((v) => ({ ...v, period: e.target.value }))} aria-label="Zeitraum">
                {periodsFor(view.interval).map((x) => <option key={x} value={x}>{LABEL[x]}</option>)}
              </select>
            </>
          ) : (
            <div className="seg" role="group" aria-label="Zeitraum">
              {ranges.map((r) => <button key={r.id} className={rangeId === r.id ? "on" : ""} onClick={() => setView({ period: r.period, interval: r.interval })}>{r.label}</button>)}
            </div>
          )}
          {meta?.native_currency && (
            <select value={ccyValue} onChange={(e) => setCcy(e.target.value)} aria-label="Währung">
              {["native", "EUR", "USD", "CHF", "GBP"].map((c) => (
                <option key={c} value={c}>{c === "native" ? `${CURRENCY_LABEL.native} (${meta.native_currency})` : CURRENCY_LABEL[c]}</option>
              ))}
            </select>
          )}
          <select value={chartType || (pro ? "candles" : "area")} onChange={(e) => pickType(e.target.value)} aria-label="Darstellung">
            {CHART_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
          <button className="opts-btn" onClick={() => setOptsOpen((o) => !o)} aria-expanded={optsOpen}>{optsOpen ? "Fertig" : "Anzeige ▾"}</button>
          <Link className="big-chart" to={`/charts/${encodeURIComponent(symbol)}`} title="Im großen Chart öffnen (Zeichnen, Indikatoren)">⛶ Groß</Link>
          <span className="toolbar-gap" />
          <label className="check"><input type="checkbox" checked={showEvents} onChange={(e) => setShowEvents(e.target.checked)} /> Signale</label>
          <label className="check"><input type="checkbox" checked={showPlan} onChange={(e) => { setPlanTouched(true); setShowPlan(e.target.checked); }} /> Einstiegsmarken</label>
          {pro && <label className="check"><input type="checkbox" checked={showSma} onChange={(e) => setShowSma(e.target.checked)} /> <Term name="SMA">SMA</Term></label>}
          {pro && <label className="check"><input type="checkbox" checked={showBb} onChange={(e) => setShowBb(e.target.checked)} /> Bollinger</label>}
        </div>
        <ErrorText error={error} />
        {!rows && !error && <Loading text="Lade Kurse …" />}
        {rows && (
          <PriceChart key={`${symbol}-${view.interval}-${view.period}-${ccy}-${mode}`} rows={rows} simple={!pro}
            type={chartType || undefined} live={liveBar} intraday={INTRADAY.has(view.interval)}
            showSma={showSma} showBb={showBb} events={events} planLines={planLines} positions={positions} currency={cur} />
        )}
        <p className="legend small">
          {showEvents && <><span className="arrow" style={{ color: "#38bdf8" }}>▲</span>Kaufsignal <span className="arrow" style={{ color: "#e879f9" }}>▼</span>Verkaufssignal</>}
          {showPlan && <><span className="dot" style={{ background: "#6fd3c3" }} />Rücksetzer-Einstieg <span className="dot" style={{ background: "#f2b84b" }} />Ausbruch</>}
          {positions.length > 0 && <><span className="swatch gain" />Chance bis Ziel <span className="swatch loss" />Risiko bis Stopp <span className="dot" style={{ background: "#f2b84b" }} />dein Kaufkurs</>}
          {pro && showSma && <><span className="dot" style={{ background: "#f2b84b" }} />SMA 20 <span className="dot" style={{ background: "#7aa7ff" }} />SMA 50 <span className="dot" style={{ background: "#c792ea" }} />SMA 200</>}
        </p>
      </section>

      {analysis && (
        <>
          <EntryPlan symbol={symbol} plan={analysis.entry} currency={analysis.currency} nativeCurrency={analysis.native_currency} held={held} />

          <details className="panel details-pro" open={pro}>
            <summary><h2>Details für Profis</h2><span className="muted small">Indikatoren, Kennzahlen und Einzelsignale</span></summary>
            <div className="analysis-grid">
              <div>
                <h3 className="sub-title">Signale</h3>
                {!held && <Levels rec={rec} currency={cur} />}
                {rec.notes?.length > 0 && <ul className="notes">{rec.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
                <ul className="signals">
                  {analysis.signals.map((s) => (
                    <li key={s.name + s.text} className={tone(s.score)}>
                      <span className="sig-score">{s.score > 0 ? `+${s.score}` : s.score}</span>
                      <span><strong>{["RSI", "MACD", "ADX", "Bollinger", "Trend"].includes(s.name) ? <Term name={s.name} /> : s.name}</strong> {s.text}{s.weight !== 1 && <span className="muted small"> · Gewicht {s.weight.toLocaleString("de-DE")}×</span>}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="sub-title">Kennzahlen</h3>
                <div className="stats stats-wide">
                  <Stat label="RSI 14" term="RSI" value={num(m.rsi, 1)} />
                  <Stat label="MACD Hist." term="MACD" value={num(m.hist, 3)} />
                  <Stat label="ADX" term="ADX" value={num(m.adx, 1)} />
                  <Stat label="Bollinger %B" term="Bollinger" value={num(m.bb_pctb, 2)} />
                  <Stat label="ATR" term="ATR" value={`${num(m.atr_pct, 2)} %`} />
                  <Stat label="SMA 200" term="SMA" value={p(m.sma200)} />
                  <Stat label="1 Monat" value={pct(m.perf_1m, 1)} className={tone(m.perf_1m)} />
                  <Stat label="3 Monate" value={pct(m.perf_3m, 1)} className={tone(m.perf_3m)} />
                  <Stat label="12 Monate" value={pct(m.perf_12m, 1)} className={tone(m.perf_12m)} />
                  <Stat label="Unterstützung" term="Unterstützung" value={p(analysis.support)} />
                  <Stat label="Widerstand" term="Widerstand" value={p(analysis.resistance)} />
                </div>
              </div>
            </div>
          </details>

          <section className="panel">
            <div className="panel-head">
              <h2>Nachrichten</h2>
              <Link className="link small" to="/settings#news">Quellen</Link>
            </div>
            <NewsList items={analysis.news} initial={5}
              empty={analysis.news_sources?.length ? `In den letzten Tagen keine Meldungen zu ${displayName(meta || analysis) || "diesem Wert"} gefunden.` : "Alle Nachrichtenquellen sind ausgeschaltet (Einstellungen → Nachrichten)."} />
          </section>
        </>
      )}
      </div>
      </div>

      {selling && openBlocks.length > 0 && (
        <SellDialog blocks={openBlocks} initialId={selling.id} live={livePrice} liveCcy={cur}
          name={info?.name} onClose={() => setSelling(null)} onSaved={refreshAll} />
      )}
      {buying && (
        <BuyDialog symbol={symbol} info={{ ...meta, price: livePrice }}
          defaults={{ price: livePrice ? Math.round(livePrice * 100) / 100 : "", stop: bestSetup?.stop ?? rec?.stop ?? "",
            target: bestSetup?.target ?? rec?.target ?? "", quantity: bestSetup?.position?.shares ?? rec?.position?.shares ?? "",
            trail_pct: rec?.trail_pct ?? null }}
          onClose={() => setBuying(false)} onSaved={refreshAll} />
      )}
    </>
  );
}
