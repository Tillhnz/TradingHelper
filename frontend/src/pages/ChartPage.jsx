import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import BuyDialog from "../components/BuyDialog.jsx";
import EntryPlan from "../components/EntryPlan.jsx";
import HoldingPanel from "../components/HoldingPanel.jsx";
import PriceChart from "../components/PriceChart.jsx";
import Term from "../components/Term.jsx";
import { ActionBadge, ErrorText, Levels, Loading, Stat } from "../components/ui.jsx";
import { CURRENCY_LABEL, dateTime, money, num, pct, signed, tone } from "../fmt.js";
import { useMode } from "../mode.js";
import { ACTION_UI, displayTicker } from "../texts.js";

const RANGES = [
  { id: "1mo", label: "1 M", period: "1mo", interval: "1d" },
  { id: "3mo", label: "3 M", period: "3mo", interval: "1d" },
  { id: "6mo", label: "6 M", period: "6mo", interval: "1d" },
  { id: "1y", label: "1 J", period: "1y", interval: "1d" },
  { id: "5y", label: "5 J", period: "5y", interval: "1wk" },
];
const PRO_PERIODS = {
  "1d": ["3mo", "6mo", "1y", "2y", "5y"],
  "1wk": ["1y", "2y", "5y", "10y"],
  "1h": ["1mo", "3mo", "6mo"],
  "15m": ["5d", "1mo"],
};
const LABEL = { "5d": "5 Tage", "1mo": "1 Monat", "3mo": "3 Monate", "6mo": "6 Monate", "1y": "1 Jahr", "2y": "2 Jahre", "5y": "5 Jahre", "10y": "10 Jahre" };
const INTERVAL_LABEL = { "1d": "Tag", "1wk": "Woche", "1h": "Stunde", "15m": "15 Min" };
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
  const [ccy, setCcy] = useState(null); // null = Einstellung
  const [meta, setMeta] = useState(null);
  const [rows, setRows] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [watched, setWatched] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [buying, setBuying] = useState(false);
  const [tick, setTick] = useState(0);
  const [holding, setHolding] = useState(null);
  const refreshAll = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    setHolding(null);
    setMeta(null);
    api.get(`/holdings/${encodeURIComponent(symbol)}`).then(setHolding).catch(() => setHolding(null));
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
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [symbol, q]);

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

  function setProInterval(iv) {
    const periods = PRO_PERIODS[iv];
    setView((v) => ({ interval: iv, period: periods.includes(v.period) ? v.period : periods[Math.min(1, periods.length - 1)] }));
  }

  const m = analysis?.metrics || {};
  const rec = analysis?.recommendation;
  const cur = meta?.currency ?? analysis?.currency;
  const p = (v) => money(v, cur);
  const ccyValue = ccy || meta?.display_currency || "native";
  const held = holding?.summary?.shares > 0;
  const last = rows?.[rows.length - 1];
  const prevRow = rows?.[rows.length - 2];
  const livePrice = view.interval === "1d" && last ? last.close : analysis?.last_close;
  const liveChange = view.interval === "1d" && last && prevRow ? (last.close / prevRow.close - 1) * 100 : analysis?.change_pct_1d;
  const bestSetup = analysis?.entry?.setups?.find((x) => x.ok && x.status === "now") || analysis?.entry?.setups?.find((x) => x.ok);
  const info = meta || analysis;
  const ui = rec ? ACTION_UI[rec.action] : null;
  const rangeId = RANGES.find((r) => r.period === view.period && r.interval === view.interval)?.id;
  const intervals = Object.keys(PRO_PERIODS).filter((iv) => meta?.intraday !== false || ["1d", "1wk"].includes(iv));

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
          {meta && <p className={`muted small ${meta.delay_min ? "delayed" : ""}`}><Term name="Verzögerung">{freshness(meta)}</Term>{meta.native_currency && meta.currency !== meta.native_currency && ` · umgerechnet in ${meta.currency}`}</p>}
        </div>
        <div className="stock-actions-top">
          <button className="btn primary" onClick={() => setBuying(true)}>{held ? "Nachkauf erfassen" : "Kauf erfassen"}</button>
          {watched !== null && !held && <button className="btn" onClick={toggleWatch}>{watched ? "✓ Beobachtet" : "☆ Beobachten"}</button>}
          <Link className="btn" to={`/alerts?symbol=${encodeURIComponent(symbol)}`}>🔔 Alarm</Link>
        </div>
      </div>
      {msg && <p className="ok" role="status">{msg}</p>}

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

      <HoldingPanel holding={holding} onChanged={refreshAll} onBuyMore={() => setBuying(true)} />

      <section className="panel chart-panel">
        <div className="toolbar">
          {pro ? (
            <>
              <div className="seg" role="group" aria-label="Kerzen">
                {intervals.map((iv) => <button key={iv} className={iv === view.interval ? "on" : ""} onClick={() => setProInterval(iv)}>{INTERVAL_LABEL[iv]}</button>)}
              </div>
              <select value={view.period} onChange={(e) => setView((v) => ({ ...v, period: e.target.value }))} aria-label="Zeitraum">
                {PRO_PERIODS[view.interval].map((x) => <option key={x} value={x}>{LABEL[x]}</option>)}
              </select>
            </>
          ) : (
            <div className="seg" role="group" aria-label="Zeitraum">
              {RANGES.map((r) => <button key={r.id} className={rangeId === r.id ? "on" : ""} onClick={() => setView({ period: r.period, interval: r.interval })}>{r.label}</button>)}
            </div>
          )}
          {meta?.native_currency && (
            <select value={ccyValue} onChange={(e) => setCcy(e.target.value)} aria-label="Währung">
              {["native", "EUR", "USD", "CHF", "GBP"].map((c) => (
                <option key={c} value={c}>{c === "native" ? `${CURRENCY_LABEL.native} (${meta.native_currency})` : CURRENCY_LABEL[c]}</option>
              ))}
            </select>
          )}
          <span className="toolbar-gap" />
          <label className="check"><input type="checkbox" checked={showEvents} onChange={(e) => setShowEvents(e.target.checked)} /> Signale</label>
          <label className="check"><input type="checkbox" checked={showPlan} onChange={(e) => setShowPlan(e.target.checked)} /> Einstiegsmarken</label>
          {pro && <label className="check"><input type="checkbox" checked={showSma} onChange={(e) => setShowSma(e.target.checked)} /> <Term name="SMA">SMA</Term></label>}
          {pro && <label className="check"><input type="checkbox" checked={showBb} onChange={(e) => setShowBb(e.target.checked)} /> Bollinger</label>}
        </div>
        <ErrorText error={error} />
        {!rows && !error && <Loading text="Lade Kurse …" />}
        {rows && (
          <PriceChart key={`${symbol}-${view.interval}-${view.period}-${ccy}-${mode}`} rows={rows} simple={!pro}
            showSma={showSma} showBb={showBb} events={events} planLines={planLines} positions={positions} />
        )}
        <p className="legend small">
          {showEvents && <><span className="arrow pos">▲</span>Kaufsignal <span className="arrow neg">▼</span>Verkaufssignal</>}
          {showPlan && <><span className="dot" style={{ background: "#6fd3c3" }} />Rücksetzer-Einstieg <span className="dot" style={{ background: "#f2b84b" }} />Ausbruch</>}
          {positions.length > 0 && <><span className="swatch gain" />im Gewinn <span className="swatch loss" />im Verlust (ab deinem Kaufkurs)</>}
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
            <h2>Nachrichten</h2>
            {analysis.news.length ? (
              <ul className="news">
                {analysis.news.map((n) => (
                  <li key={n.url || n.headline}>
                    <span className={`sent ${tone(n.sentiment)}`} title="Stimmung der Schlagzeile">{n.sentiment > 0.15 ? "positiv" : n.sentiment < -0.15 ? "negativ" : "neutral"}</span>
                    <a href={n.url} target="_blank" rel="noreferrer noopener">{n.headline}</a>
                    <span className="muted small"> · {n.source} · {dateTime(n.published)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Keine aktuellen Nachrichten gefunden. Ohne Finnhub-Schlüssel (Einstellungen) gibt es keine News; für europäische Werte liefert Finnhub oft wenig.</p>
            )}
          </section>
        </>
      )}

      {buying && (
        <BuyDialog symbol={symbol} info={{ ...meta, price: livePrice }}
          defaults={{ price: livePrice ? Math.round(livePrice * 100) / 100 : "", stop: bestSetup?.stop ?? rec?.stop ?? "",
            target: bestSetup?.target ?? rec?.target ?? "", quantity: bestSetup?.position?.shares ?? rec?.position?.shares ?? "" }}
          onClose={() => setBuying(false)} onSaved={refreshAll} />
      )}
    </>
  );
}
