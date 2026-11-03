import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import PriceChart from "../components/PriceChart.jsx";
import { ActionBadge, ErrorText, Loading, Stat } from "../components/ui.jsx";
import { Levels } from "./Home.jsx";
import EntryPlan from "../components/EntryPlan.jsx";
import BuyDialog from "../components/BuyDialog.jsx";
import { CURRENCY_LABEL, dateTime, money, num, pct, signed, tone } from "../fmt.js";

// Yahoo liefert Intraday-Daten nur für begrenzte Zeiträume
const PERIODS = {
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

function delayText(meta) {
  if (!meta) return "";
  const when = meta.as_of ? new Date(meta.as_of * 1000).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : null;
  const delay = meta.delay_min === 0 ? "Echtzeit" : meta.delay_min ? `ca. ${meta.delay_min} Min. verzögert` : "Verzögerung unbekannt";
  return [when && `Stand ${when}`, delay, meta.quote_source].filter(Boolean).join(" · ");
}

export default function ChartPage() {
  const { symbol: param } = useParams();
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState(param?.toUpperCase() || "");
  const [input, setInput] = useState(param?.toUpperCase() || "");
  const [interval, setInterval_] = useState("1d");
  const [period, setPeriod] = useState("1y");
  const [showSma, setShowSma] = useState(true);
  const [showBb, setShowBb] = useState(false);
  const [ccy, setCcy] = useState(null); // null = Einstellung
  const [meta, setMeta] = useState(null);
  const [rows, setRows] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [watch, setWatch] = useState([]);
  const [error, setError] = useState("");
  const [showEvents, setShowEvents] = useState(true);
  const [showPlan, setShowPlan] = useState(true);
  const [showPos, setShowPos] = useState(true);
  const [buying, setBuying] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api.get("/watchlist").then((w) => {
      setWatch(w.map((x) => x.symbol));
      if (!param) {
        const first = w[0]?.symbol || "AAPL";
        setSymbol(first);
        setInput(first);
      }
    }).catch(() => { if (!param) { setSymbol("AAPL"); setInput("AAPL"); } });
  }, [param]);

  useEffect(() => {
    if (param) { setSymbol(param.toUpperCase()); setInput(param.toUpperCase()); }
  }, [param]);

  useEffect(() => {
    if (!symbol) return undefined;
    let stop = false;
    setRows(null);
    setAnalysis(null);
    setError("");
    const q = `period=${period}&interval=${interval}${ccy ? `&currency=${ccy}` : ""}`;
    api.get(`/history/${encodeURIComponent(symbol)}?${q}`)
      .then((r) => { if (!stop) { setRows(r.rows); setMeta(r); } })
      .catch((e) => { if (!stop) setError(e.message); });
    // Tageskerzen: Zeitraum der Anlagestrategie, damit die Einschätzung zum Report passt
    const qa = interval === "1d" ? `interval=1d${ccy ? `&currency=${ccy}` : ""}` : q;
    api.get(`/analysis/${encodeURIComponent(symbol)}?${qa}`)
      .then((a) => { if (!stop) setAnalysis(a); })
      .catch(() => {});
    return () => { stop = true; };
  }, [symbol, period, interval, ccy, tick]);

  // Kurse automatisch nachladen, solange die Seite sichtbar ist (still, ohne Ladeanzeige)
  useEffect(() => {
    if (!symbol) return undefined;
    const q = `period=${period}&interval=${interval}${ccy ? `&currency=${ccy}` : ""}`;
    const id = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      api.get(`/history/${encodeURIComponent(symbol)}?${q}`).then((r) => { setRows(r.rows); setMeta(r); }).catch(() => {});
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [symbol, period, interval, ccy]);

  const planLines = useMemo(() => {
    if (!analysis) return [];
    const lines = [
      { price: analysis.support, color: "rgba(111, 211, 195, 0.45)", title: "Unterstützung", style: 2 },
      { price: analysis.resistance, color: "rgba(255, 107, 107, 0.45)", title: "Widerstand", style: 2 },
    ];
    if (!showPlan || !analysis.entry) return lines;
    const ok = analysis.entry.setups.filter((x) => x.ok);
    ok.forEach((x) => {
      if (x.kind !== "now") lines.push({ price: x.entry, color: KIND_COLOR[x.kind], title: KIND_TITLE[x.kind], width: 2, style: 0 });
    });
    const best = ok.find((x) => x.status === "now") || [...ok].sort((a, b) => Math.abs(a.distance_pct) - Math.abs(b.distance_pct))[0];
    if (best) {
      lines.push({ price: best.stop, color: "#ff6b6b", title: "Stopp (Plan)", style: 3 });
      if (best.target) lines.push({ price: best.target, color: "#6fd3c3", title: "Ziel (Plan)", style: 3 });
    }
    return lines;
  }, [analysis, showPlan]);

  const events = useMemo(() => (showEvents && meta?.events ? meta.events : []), [meta, showEvents]);
  const positions = useMemo(() => (showPos && meta?.positions ? meta.positions : []), [meta, showPos]);
  const keepRange = useCallback(() => {}, []);

  function go(e) {
    e.preventDefault();
    const s = input.trim().toUpperCase();
    if (s) navigate(`/chart/${encodeURIComponent(s)}`);
  }

  function changeInterval(iv) {
    setInterval_(iv);
    if (!PERIODS[iv].includes(period)) setPeriod(PERIODS[iv][Math.min(1, PERIODS[iv].length - 1)]);
  }

  async function addToWatchlist() {
    try {
      await api.post("/watchlist", { symbol });
      setWatch((w) => [...w, symbol]);
    } catch (e) {
      setError(e.message);
    }
  }

  const m = analysis?.metrics || {};
  const cur = meta?.currency;
  const p = (v) => money(v, cur);
  const ccyValue = ccy || meta?.display_currency || "native";
  const rec = analysis?.recommendation;
  const last = rows?.[rows.length - 1];
  const prevRow = rows?.[rows.length - 2];
  const livePrice = interval === "1d" && last ? last.close : analysis?.last_close;
  const liveChange = interval === "1d" && last && prevRow ? (last.close / prevRow.close - 1) * 100 : analysis?.change_pct_1d;
  const bestSetup = analysis?.entry?.setups?.find((x) => x.ok && x.status === "now") || analysis?.entry?.setups?.find((x) => x.ok);

  return (
    <>
      <div className="page-head">
        <div className="chart-title">
          <h1>{symbol || "Chart"}</h1>
          {livePrice != null && (
            <span className="chart-quote">
              <strong>{p(livePrice)}</strong>
              <span className={tone(liveChange)}>{pct(liveChange)}</span>
            </span>
          )}
          {meta && (meta.name || meta.exchange) && (
            <p className="muted chart-sub">
              {[meta.name, meta.exchange && `${meta.exchange}${meta.native_currency ? ` (${meta.native_currency})` : ""}`].filter(Boolean).join(" · ")}
              {meta.native_currency && meta.currency !== meta.native_currency && ` · umgerechnet in ${meta.currency}`}
            </p>
          )}
          {meta && <p className={`muted small chart-sub ${meta.delay_min ? "delayed" : ""}`}>{delayText(meta)} · aktualisiert sich jede Minute</p>}
        </div>
        <form className="symbol-form" onSubmit={go}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Symbol" aria-label="Symbol" list="watch-symbols" />
          <datalist id="watch-symbols">{watch.map((s) => <option key={s} value={s} />)}</datalist>
          <button className="btn">Öffnen</button>
        </form>
      </div>

      <div className="toolbar">
        <div className="seg" role="group" aria-label="Kerzen">
          {Object.keys(PERIODS).map((iv) => (
            <button key={iv} className={iv === interval ? "on" : ""} onClick={() => changeInterval(iv)}>{INTERVAL_LABEL[iv]}</button>
          ))}
        </div>
        <select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Zeitraum">
          {PERIODS[interval].map((p) => <option key={p} value={p}>{LABEL[p]}</option>)}
        </select>
        {meta?.native_currency && (
          <select value={ccyValue} onChange={(e) => setCcy(e.target.value)} aria-label="Währung">
            {["native", "EUR", "USD", "CHF", "GBP"].map((c) => (
              <option key={c} value={c}>{c === "native" ? `${CURRENCY_LABEL.native} (${meta.native_currency})` : CURRENCY_LABEL[c]}</option>
            ))}
          </select>
        )}
        <label className="check"><input type="checkbox" checked={showSma} onChange={(e) => setShowSma(e.target.checked)} /> SMA 20/50/200</label>
        <label className="check"><input type="checkbox" checked={showBb} onChange={(e) => setShowBb(e.target.checked)} /> Bollinger</label>
        <label className="check"><input type="checkbox" checked={showEvents} onChange={(e) => setShowEvents(e.target.checked)} /> Signale</label>
        <label className="check"><input type="checkbox" checked={showPlan} onChange={(e) => setShowPlan(e.target.checked)} /> Einstiegsplan</label>
        {meta?.positions?.length > 0 && <label className="check"><input type="checkbox" checked={showPos} onChange={(e) => setShowPos(e.target.checked)} /> Meine Käufe</label>}
        <span className="toolbar-gap" />
        {symbol && <button className="btn small primary" onClick={() => setBuying(true)}>Kauf erfassen</button>}
        {symbol && !watch.includes(symbol) && <button className="btn small" onClick={addToWatchlist}>Zur Watchlist</button>}
        {symbol && <Link className="btn small" to={`/alerts?symbol=${encodeURIComponent(symbol)}`}>Alarm anlegen</Link>}
      </div>

      <ErrorText error={error} />
      {!rows && !error && <Loading text="Lade Kurse …" />}
      {rows && (
        <div className="panel chart-panel">
          <PriceChart key={`${symbol}-${interval}-${period}-${ccy}`} rows={rows} showSma={showSma} showBb={showBb}
            events={events} planLines={planLines} positions={positions} onVisibleRange={keepRange} />
          <p className="legend small">
            {showSma && <><span className="dot" style={{ background: "#f2b84b" }} />SMA 20
              <span className="dot" style={{ background: "#7aa7ff" }} />SMA 50
              <span className="dot" style={{ background: "#c792ea" }} />SMA 200</>}
            {showEvents && <><span className="arrow pos">▲</span>Kaufsignal <span className="arrow neg">▼</span>Verkaufssignal</>}
            {showPlan && <><span className="dot" style={{ background: "#6fd3c3" }} />Rücksetzer <span className="dot" style={{ background: "#f2b84b" }} />Ausbruch</>}
            {positions.length > 0 && <><span className="swatch gain" />Gewinnzone <span className="swatch loss" />Verlustzone ab Kaufkurs</>}
          </p>
        </div>
      )}

      {buying && (
        <BuyDialog symbol={symbol} info={{ ...meta, price: livePrice }}
          defaults={{ price: livePrice ? Math.round(livePrice * 100) / 100 : "", stop: bestSetup?.stop ?? rec?.stop ?? "",
            target: bestSetup?.target ?? rec?.target ?? "", quantity: bestSetup?.position?.shares ?? rec?.position?.shares ?? "" }}
          onClose={() => setBuying(false)} onSaved={() => setTick((t) => t + 1)} />
      )}

      {analysis && (
        <div className="analysis-grid">
          <section className="panel">
            <div className="panel-head">
              <h2>Einschätzung</h2>
              <ActionBadge action={rec.action} />
            </div>
            <p className="muted small">Strategie <Link to="/settings">{rec.profile}</Link>{interval !== "1d" && ` · auf ${INTERVAL_LABEL[interval]}-Kerzen`}</p>
            <div className="stats">
              <Stat label="Gesamt" value={signed(rec.combined)} className={tone(rec.combined)} />
              <Stat label="Technik" value={signed(rec.technical)} className={tone(rec.technical)} />
              <Stat label="News" value={rec.sentiment === null ? "–" : signed(rec.sentiment)} className={tone(rec.sentiment)} />
            </div>
            <Levels rec={rec} currency={cur} />
            {rec.notes?.length > 0 && <ul className="notes">{rec.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
            <ul className="signals">
              {analysis.signals.map((s) => (
                <li key={s.name + s.text} className={tone(s.score)}>
                  <span className="sig-score">{s.score > 0 ? `+${s.score}` : s.score}</span>
                  <span><strong>{s.name}</strong> {s.text}{s.weight !== 1 && <span className="muted small"> · Gewicht {s.weight.toLocaleString("de-DE")}×</span>}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="panel">
            <h2>Kennzahlen</h2>
            <div className="stats stats-wide">
              <Stat label="RSI 14" value={num(m.rsi, 1)} />
              <Stat label="MACD Hist." value={num(m.hist, 3)} />
              <Stat label="ADX" value={num(m.adx, 1)} />
              <Stat label="Stoch %K" value={num(m.stoch_k, 1)} />
              <Stat label="Bollinger %B" value={num(m.bb_pctb, 2)} />
              <Stat label="ATR" value={`${num(m.atr_pct, 2)} %`} />
              <Stat label="SMA 50" value={p(m.sma50)} />
              <Stat label="SMA 200" value={p(m.sma200)} />
              <Stat label="1 Monat" value={pct(m.perf_1m, 1)} className={tone(m.perf_1m)} />
              <Stat label="3 Monate" value={pct(m.perf_3m, 1)} className={tone(m.perf_3m)} />
              <Stat label="Unterstützung" value={p(analysis.support)} />
              <Stat label="Widerstand" value={p(analysis.resistance)} />
            </div>
          </section>
          <EntryPlan symbol={symbol} plan={analysis.entry} currency={analysis.currency} nativeCurrency={analysis.native_currency} />
          <section className="panel span-all">
            <h2>Nachrichten</h2>
            {analysis.news.length ? (
              <ul className="news">
                {analysis.news.map((n) => (
                  <li key={n.url || n.headline}>
                    <span className={`sent ${tone(n.sentiment)}`}>{signed(n.sentiment)}</span>
                    <a href={n.url} target="_blank" rel="noreferrer noopener">{n.headline}</a>
                    <span className="muted small"> · {n.source} · {dateTime(n.published)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">Keine Nachrichten gefunden. Ohne Finnhub-Schlüssel (Einstellungen) gibt es keine News; für europäische Werte liefert Finnhub oft wenig.</p>
            )}
          </section>
        </div>
      )}
    </>
  );
}
