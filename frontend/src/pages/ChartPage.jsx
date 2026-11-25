import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import BuyDialog from "../components/BuyDialog.jsx";
import EntryPlan from "../components/EntryPlan.jsx";
import HoldingPanel from "../components/HoldingPanel.jsx";
import BreakoutMeter from "../components/BreakoutMeter.jsx";
import CompanyPanel from "../components/CompanyPanel.jsx";
import Icon from "../components/Icon.jsx";
import { BAR_SECONDS, INTRADAY, pickResolution, RANGES, rangeAvailable } from "../intervals.js";
import SellDialog from "../components/SellDialog.jsx";
import NewsList from "../components/NewsList.jsx";
import { ModelCard, SocialCard, WhyCard } from "../components/InsightCards.jsx";
import PriceChart from "../components/PriceChart.jsx";
import Term from "../components/Term.jsx";
import { ActionBadge, ErrorText, Levels, Loading, Stat } from "../components/ui.jsx";
import { CURRENCY_LABEL, money, num, pct, signed, tone } from "../fmt.js";
import { since, useLiveQuotes } from "../live.js";
import { useMode } from "../mode.js";
import { ACTION_UI, displayName, displayTicker } from "../texts.js";

const REFRESH_MS = 60 * 1000;

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
  const [range, setRange] = useState("1y");
  const [meta, setMeta] = useState(null);
  // Kleiner Chart: nur der Zeitraum ist wählbar, die Auflösung ergibt sich daraus (feiner im großen Chart)
  const view = { period: RANGES.find((r) => r.id === range)?.period || "1y", interval: pickResolution(range, null, meta) };
  const [ccy, setCcy] = useState(null); // null = Einstellung
  const [rows, setRows] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [watched, setWatched] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [buying, setBuying] = useState(false);
  const [selling, setSelling] = useState(null);
  const [tick, setTick] = useState(0);
  const [holding, setHolding] = useState(null);
  const refreshAll = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    setHolding(null);
    setMeta(null);
    api.get(`/holdings/${encodeURIComponent(symbol)}`).then((h) => {
      setHolding(h);
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
  // Die Meinung darf kippen: Rät die Halter-Sicht zum Verkauf (z. B. Rutsch wahrscheinlich), zeigt das Abzeichen das auch
  const adv = holding?.summary?.advice;
  const shownAction = rec && held && adv?.reason === "rethink" && adv.level === "bad" ? "Reduzieren prüfen" : rec?.action;
  const ui = shownAction ? ACTION_UI[shownAction] : null;

  return (
    <>
      <div className="stock-head">
        <div className="stock-id">
          <Link to="/watchlist" className="back-link small"><Icon name="back" /> Meine Werte</Link>
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
          <button className="btn primary btn-buy" onClick={() => setBuying(true)} title="Kurs und Uhrzeit von jetzt übernehmen"><Icon name="buy" /> {held ? "Nachkauf" : "Kauf"}</button>
          {held && <button className="btn btn-sell" onClick={() => setSelling({})} title="Kurs und Uhrzeit von jetzt übernehmen"><Icon name="sell" /> Verkauf</button>}
          {watched !== null && !held && <button className={`btn ${watched ? "on" : ""}`} onClick={toggleWatch}><Icon name={watched ? "check" : "star"} /> {watched ? "Beobachtet" : "Beobachten"}</button>}
          <Link className="btn" to={`/alerts?symbol=${encodeURIComponent(symbol)}`}><Icon name="bell" /> Alarm</Link>
          <Link className="btn" to={`/charts/${encodeURIComponent(symbol)}`} title="Großer Chart: Linien und Kennlinien selbst einzeichnen"><Icon name="expand" /> Großer Chart</Link>
        </div>
      </div>
      {msg && <p className="ok" role="status">{msg}</p>}
      <nav className="jump-nav" aria-label="Auf dieser Seite">
        <a href="#chart"><Icon name="activity" /> Chart</a>
        <a href="#warum"><Icon name="info" /> Warum?</a>
        {analysis?.breakout && <a href="#ausbruch"><Icon name="zap" /> Ausbruch</a>}
        {holding?.items?.length > 0 && <a href="#bestand"><Icon name="briefcase" /> Bestand</a>}
        {analysis && <a href="#plan"><Icon name="target" /> Einstieg</a>}
        <a href="#firma"><Icon name="building" /> Unternehmen</a>
        {analysis && <a href="#modell"><Icon name="brain" /> Modell</a>}
        {analysis && <a href="#news"><Icon name="news" /> News</a>}
        <a href="#stimmung"><Icon name="message" /> Stimmung</a>
      </nav>

      <div className="stock-layout">
      <aside className="stock-side">
      {rec && (
        <section className={`verdict ${ui?.tone || ""}`}>
          <div className="verdict-main">
            <span className="verdict-label">{held ? "Für deinen Bestand" : "Unsere Einschätzung"}</span>
            <ActionBadge action={shownAction} held={held} large />
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

      <WhyCard symbol={symbol} />
      {analysis && <ModelCard model={analysis.model} />}
      <div id="ausbruch" className="anchor"><BreakoutMeter bo={analysis?.breakout} currency={cur} /></div>
      <div id="bestand" className="anchor" />
      <HoldingPanel holding={holding} onChanged={refreshAll} onBuyMore={() => setBuying(true)} onSell={(id) => setSelling({ id })} />
      </aside>

      <div className="stock-main">
      <section className="panel chart-panel" id="chart">
        <div className="toolbar">
          <div className="seg range-seg" role="group" aria-label="Zeitraum">
            {RANGES.map((r) => {
              const ok = !meta || rangeAvailable(r.id, meta);
              return (
                <button key={r.id} className={range === r.id ? "on" : ""} disabled={!ok} onClick={() => setRange(r.id)}
                  title={ok ? undefined : "Für diesen Wert gibt es keine Kurse im Minutentakt"}>{r.label}</button>
              );
            })}
          </div>
          {meta?.native_currency && (
            <select value={ccyValue} onChange={(e) => setCcy(e.target.value)} aria-label="Währung">
              {["native", "EUR", "USD", "CHF", "GBP"].map((c) => (
                <option key={c} value={c}>{c === "native" ? `${CURRENCY_LABEL.native} (${meta.native_currency})` : CURRENCY_LABEL[c]}</option>
              ))}
            </select>
          )}
          <Link className="big-chart" to={`/charts/${encodeURIComponent(symbol)}`} title="Im großen Chart öffnen: Kerzen, Signale, Einstiegsmarken, Indikatoren, Zeichnen">⛶ Vollbild-Chart</Link>
        </div>
        <ErrorText error={error} />
        {!rows && !error && <Loading text="Lade Kurse …" />}
        {rows && (
          // Kleiner Chart: bewusst nur der Kursverlauf. Signale, Einstiegsmarken, Positionen und Indikatoren gibt es im Vollbild-Chart.
          <PriceChart key={`${symbol}-${view.interval}-${view.period}-${ccy}`} rows={rows} simple type="area"
            live={liveBar} intraday={view.interval === "1s" ? "seconds" : INTRADAY.has(view.interval)}
            showSma={false} showBb={false} currency={cur} />
        )}
      </section>

      {analysis && (
        <>
          <div id="plan" className="anchor" />
          <EntryPlan symbol={symbol} plan={analysis.entry} currency={analysis.currency} nativeCurrency={analysis.native_currency} held={held} />

          <div id="firma" className="anchor" />
          <CompanyPanel symbol={symbol} pro={pro} />

          <details className="panel details-pro" open={pro}>
            <summary><h2><Icon name="sparkles" className="h-icon" /> Details für Profis</h2><span className="muted small">Indikatoren, Kennzahlen und Einzelsignale</span></summary>
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

          <SocialCard symbol={symbol} />

          <section className="panel" id="news">
            <div className="panel-head">
              <h2><Icon name="news" className="h-icon" /> Nachrichten</h2>
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
