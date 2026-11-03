import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { ActionBadge, Empty, ErrorText, Loading } from "../components/ui.jsx";
import { dateTime, money, num, pct, signed, signedMoney, tone } from "../fmt.js";

export function Levels({ rec, currency }) {
  if (!rec.stop && !rec.target) return null;
  return (
    <div className="levels small">
      {rec.stop && <span><span className="muted">Stopp</span> {money(rec.stop, currency)}</span>}
      {rec.target && <span><span className="muted">Ziel</span> {money(rec.target, currency)}</span>}
      {rec.crv && <span><span className="muted">CRV</span> {rec.crv.toLocaleString("de-DE", { maximumFractionDigits: 1 })}</span>}
      {rec.position && (
        <span className="levels-pos">
          <span className="muted">Position</span> {rec.position.shares} Stück ≈ {money(rec.position.value, currency)}
          <span className="muted"> · Risiko {money(rec.position.risk, currency)} ({rec.position.risk_pct.toLocaleString("de-DE")} %)</span>
        </span>
      )}
    </div>
  );
}

const ORDER = { "Kaufen prüfen": 0, "Reduzieren prüfen": 1, "Halten / beobachten": 2 };

export default function Home() {
  const [report, setReport] = useState(null);
  const [log, setLog] = useState([]);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setError("");
    setReport(null);
    try {
      const [r, l] = await Promise.all([api.get("/report"), api.get("/alerts/log?limit=8")]);
      setReport(r);
      setLog(l);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function send() {
    setSending(true);
    setMsg("");
    try {
      await api.post("/report/send");
      setMsg("Report per Push verschickt.");
    } catch (e) {
      setMsg(e.message);
    } finally {
      setSending(false);
    }
  }

  const entries = report ? [...report.entries].sort((a, b) => ORDER[a.action] - ORDER[b.action] || Math.abs(b.combined_score) - Math.abs(a.combined_score)) : [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Heute</h1>
          <p className="muted">
            {report ? `Stand ${report.created}` : "Einschätzung für deine Watchlist"}
            {report?.profile && <> · Strategie <Link to="/settings">{report.profile}</Link></>}
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={!report && !error}>Aktualisieren</button>
          <button className="btn primary" onClick={send} disabled={sending || !report?.entries.length}>
            {sending ? "Sende …" : "Per Push senden"}
          </button>
        </div>
      </div>
      {msg && <p className="note" role="status">{msg}</p>}
      <ErrorText error={error} />
      {!report && !error && <Loading text="Analysiere Watchlist und Nachrichten …" />}

      {report && !report.entries.length && !Object.keys(report.errors).length && (
        <Empty title="Noch keine Werte in der Watchlist">
          <p className="muted">Füge Aktien, ETFs, Indizes oder Kryptowährungen hinzu. Jeden Morgen kommt dann eine Einschätzung aufs Handy.</p>
          <Link className="btn primary" to="/watchlist">Zur Watchlist</Link>
        </Empty>
      )}

      <div className="card-grid">
        {entries.map((e) => (
          <article key={e.symbol} className={`rec-card ${e.action === "Kaufen prüfen" ? "buy" : e.action === "Reduzieren prüfen" ? "sell" : "hold"}`}>
            <header>
              <Link to={`/chart/${encodeURIComponent(e.symbol)}`} className="rec-symbol">{e.symbol}</Link>
              <ActionBadge action={e.action} />
            </header>
            {(e.name || e.exchange) && <p className="muted small rec-sub">{[e.name, e.exchange].filter(Boolean).join(" · ")}</p>}
            <div className="rec-price">
              <strong>{money(e.analysis.last_close, e.currency)}</strong>
              <span className={tone(e.analysis.change_pct_1d)}>{pct(e.analysis.change_pct_1d)}</span>
            </div>
            <div className="score-bar" aria-label={`Score ${signed(e.combined_score)}`}>
              <span style={{ left: `${((e.combined_score + 1) / 2) * 100}%` }} />
            </div>
            <p className="muted small">
              Score {signed(e.combined_score)} · Technik {signed(e.technical_score)}
              {e.sentiment !== null && ` · News ${signed(e.sentiment)}`}
            </p>
            <ul className="reasons">
              {e.reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
            {e.holding?.shares > 0 && (
              <Link to={`/chart/${encodeURIComponent(e.symbol)}`} className="home-holding">
                <span>💼 Im Depot: {num(e.holding.shares, e.holding.shares % 1 ? 3 : 0)} Stück</span>
                {e.holding.pl != null && <strong className={tone(e.holding.pl)}>{signedMoney(e.holding.pl, e.holding.currency)} ({pct(e.holding.pl_pct, 1)})</strong>}
                {e.holding.advice && <span className={`advice-inline ${e.holding.advice.level}`}>{e.holding.advice.text}</span>}
              </Link>
            )}
            {!e.holding?.shares && <Levels rec={e} currency={e.currency} />}
            {!e.holding?.shares && e.entry && e.action !== "Kaufen prüfen" && (
              <p className="entry-line small"><Link to={`/chart/${encodeURIComponent(e.symbol)}`}>Einstieg</Link>: {e.entry.summary}</p>
            )}
            {e.news[0] && (
              <a className="headline small" href={e.news[0].url} target="_blank" rel="noreferrer noopener">
                {e.news[0].headline}
              </a>
            )}
          </article>
        ))}
      </div>

      {report && Object.entries(report.errors).map(([sym, err]) => (
        <p key={sym} className="error small">{sym}: {err}</p>
      ))}

      <h2 className="section-title">Letzte Alarme</h2>
      {log.length ? (
        <ul className="log-list">
          {log.map((l) => (
            <li key={l.id}><span className="muted small">{dateTime(l.triggered_at)}</span> <strong>{l.symbol}</strong> {l.message}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">Noch keine Alarme ausgelöst. <Link to="/alerts">Alarme einrichten</Link></p>
      )}
    </>
  );
}
