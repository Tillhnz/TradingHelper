import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import PriceChart from "../components/PriceChart.jsx";
import { ActionBadge, ErrorText, Loading, Stat } from "../components/ui.jsx";
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
    api.get(`/analysis/${encodeURIComponent(symbol)}?${q}`)
      .then((a) => { if (!stop) setAnalysis(a); })
      .catch(() => {});
    return () => { stop = true; };
  }, [symbol, period, interval, ccy]);

  const levels = useMemo(() => (analysis ? [
    { price: analysis.support, color: "#6fd3c3", title: "Unterstützung" },
    { price: analysis.resistance, color: "#ff6b6b", title: "Widerstand" },
  ] : []), [analysis]);

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

  return (
    <>
      <div className="page-head">
        <div className="chart-title">
          <h1>{symbol || "Chart"}</h1>
          {analysis && (
            <span className="chart-quote">
              <strong>{p(analysis.last_close)}</strong>
              <span className={tone(analysis.change_pct_1d)}>{pct(analysis.change_pct_1d)}</span>
            </span>
          )}
          {meta && (meta.name || meta.exchange) && (
            <p className="muted chart-sub">
              {[meta.name, meta.exchange && `${meta.exchange}${meta.native_currency ? ` (${meta.native_currency})` : ""}`].filter(Boolean).join(" · ")}
              {meta.native_currency && meta.currency !== meta.native_currency && ` · umgerechnet in ${meta.currency}`}
            </p>
          )}
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
        <span className="toolbar-gap" />
        {symbol && !watch.includes(symbol) && <button className="btn small" onClick={addToWatchlist}>Zur Watchlist</button>}
        {symbol && <Link className="btn small" to={`/alerts?symbol=${encodeURIComponent(symbol)}`}>Alarm anlegen</Link>}
      </div>

      <ErrorText error={error} />
      {!rows && !error && <Loading text="Lade Kurse …" />}
      {rows && (
        <div className="panel chart-panel">
          <PriceChart rows={rows} showSma={showSma} showBb={showBb} levels={levels} />
          {showSma && (
            <p className="legend small">
              <span className="dot" style={{ background: "#f2b84b" }} />SMA 20
              <span className="dot" style={{ background: "#7aa7ff" }} />SMA 50
              <span className="dot" style={{ background: "#c792ea" }} />SMA 200
            </p>
          )}
        </div>
      )}

      {analysis && (
        <div className="analysis-grid">
          <section className="panel">
            <div className="panel-head">
              <h2>Einschätzung</h2>
              <ActionBadge action={rec.action} />
            </div>
            <div className="stats">
              <Stat label="Gesamt" value={signed(rec.combined)} className={tone(rec.combined)} />
              <Stat label="Technik" value={signed(rec.technical)} className={tone(rec.technical)} />
              <Stat label="News" value={rec.sentiment === null ? "–" : signed(rec.sentiment)} className={tone(rec.sentiment)} />
            </div>
            <ul className="signals">
              {analysis.signals.map((s) => (
                <li key={s.name + s.text} className={tone(s.score)}>
                  <span className="sig-score">{s.score > 0 ? `+${s.score}` : s.score}</span>
                  <span><strong>{s.name}</strong> {s.text}</span>
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
