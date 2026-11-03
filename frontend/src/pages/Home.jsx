import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import Term from "../components/Term.jsx";
import { ActionBadge, ErrorText, Levels, Loading } from "../components/ui.jsx";
import { dateTime, money, num, pct, signed, signedMoney, tone } from "../fmt.js";
import { useMode } from "../mode.js";
import { ACTION_UI, displayName, displayTicker, greeting } from "../texts.js";

const ORDER = { "Kaufen prüfen": 0, "Reduzieren prüfen": 1, "Halten / beobachten": 2 };
const DISMISS_KEY = "tradehelper_onboarding_done";

function Onboarding({ settings, count }) {
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === "1"; } catch { return false; }
  });
  if (!settings || hidden) return null;
  const steps = [
    { done: count > 0, title: "Werte hinzufügen", text: "Oben nach einer Aktie oder einem ETF suchen und „Beobachten“ antippen.", to: "/watchlist", cta: "Meine Werte" },
    { done: settings.fields.ntfy_topic?.value, title: "Push aufs Handy", text: "ntfy-App installieren und das Topic in den Einstellungen eintragen.", to: "/settings", cta: "Einrichten" },
    { done: settings.fields.finnhub_api_key?.set, title: "Nachrichten einbinden", text: "Kostenlosen Finnhub-Schlüssel eintragen, damit News in die Einschätzung einfließen.", to: "/settings", cta: "Einrichten" },
    { done: settings.fields.invest_horizon?.from_ui, title: "Strategie festlegen", text: "Anlagehorizont und Risikobereitschaft wählen – danach richten sich alle Empfehlungen.", to: "/settings", cta: "Festlegen" },
  ];
  const open = steps.filter((s) => !s.done).length;
  if (!open) return null;
  return (
    <section className="panel onboarding">
      <div className="panel-head">
        <h2>Erste Schritte <span className="muted small">{steps.length - open} von {steps.length} erledigt</span></h2>
        <button className="link small" onClick={() => { try { localStorage.setItem(DISMISS_KEY, "1"); } catch { /* egal */ } setHidden(true); }}>Ausblenden</button>
      </div>
      <ol className="steps">
        {steps.map((s) => (
          <li key={s.title} className={s.done ? "done" : ""}>
            <span className="step-dot" aria-hidden="true">{s.done ? "✓" : ""}</span>
            <div><strong>{s.title}</strong><p className="muted small">{s.text}</p></div>
            {!s.done && <Link className="btn small" to={s.to}>{s.cta}</Link>}
          </li>
        ))}
      </ol>
    </section>
  );
}

function DepotStrip({ data }) {
  if (!data?.items?.length) return null;
  const t = data.totals;
  const open = data.items.filter((p) => !p.closed).length;
  return (
    <Link to="/depot" className="depot-strip">
      <div><span className="muted small">Mein Depot</span><strong>{money(t.value, t.currency)}</strong></div>
      <div><span className="muted small">Gewinn/Verlust</span><strong className={tone(t.pl)}>{signedMoney(t.pl, t.currency)} <span className="small">{pct(t.pl_pct, 1)}</span></strong></div>
      <div className="hide-sm"><span className="muted small">Positionen</span><strong>{open}</strong></div>
      <span className="depot-strip-go">Zum Depot →</span>
    </Link>
  );
}

function StockCard({ e, pro }) {
  const held = e.holding?.shares > 0;
  const ui = ACTION_UI[e.action];
  const to = `/chart/${encodeURIComponent(e.symbol)}`;
  return (
    <article className={`rec-card ${ui?.tone || ""}`}>
      <header>
        <Link to={to} className="rec-title">
          <strong>{displayName(e)}</strong>
          <span className="muted small">{displayTicker(e)}{e.exchange ? ` · ${e.exchange}` : ""}</span>
        </Link>
        <ActionBadge action={e.action} held={held} />
      </header>
      <div className="rec-price">
        <strong>{money(e.analysis.last_close, e.currency)}</strong>
        <span className={tone(e.analysis.change_pct_1d)}>{pct(e.analysis.change_pct_1d)}</span>
        <span className="muted small">heute</span>
      </div>

      {held && (
        <Link to={to} className="home-holding">
          <span>💼 Du hast {num(e.holding.shares, e.holding.shares % 1 ? 3 : 0)} Stück</span>
          {e.holding.pl != null && <strong className={tone(e.holding.pl)}>{signedMoney(e.holding.pl, e.holding.currency)} ({pct(e.holding.pl_pct, 1)})</strong>}
          {e.holding.advice && <span className={`advice-inline ${e.holding.advice.level}`}>{e.holding.advice.text}</span>}
        </Link>
      )}

      {pro ? (
        <>
          <div className="score-bar" aria-label={`Score ${signed(e.combined_score)}`}><span style={{ left: `${((e.combined_score + 1) / 2) * 100}%` }} /></div>
          <p className="muted small"><Term name="Score">Score</Term> {signed(e.combined_score)} · Technik {signed(e.technical_score)}{e.sentiment !== null && ` · News ${signed(e.sentiment)}`}</p>
          <ul className="reasons">{e.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          {!held && <Levels rec={e} currency={e.currency} />}
        </>
      ) : (
        <p className="rec-why"><span className="muted">Warum?</span> {e.reasons[0]}</p>
      )}

      {!held && e.entry && (
        <p className="next-step small"><span className="muted">Nächster Schritt:</span> {e.entry.summary}</p>
      )}
      {e.news[0] && pro && (
        <a className="headline small" href={e.news[0].url} target="_blank" rel="noreferrer noopener">{e.news[0].headline}</a>
      )}
      <Link to={to} className="card-more">Details ansehen →</Link>
    </article>
  );
}

export default function Home() {
  const { mode } = useMode();
  const [report, setReport] = useState(null);
  const [log, setLog] = useState([]);
  const [settings, setSettings] = useState(null);
  const [depot, setDepot] = useState(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    setError("");
    setReport(null);
    api.get("/settings").then(setSettings).catch(() => {});
    api.get("/positions").then(setDepot).catch(() => {});
    api.get("/alerts/log?limit=6").then(setLog).catch(() => {});
    try {
      setReport(await api.get("/report"));
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
      setMsg("Zusammenfassung per Push verschickt.");
    } catch (e) {
      setMsg(e.message);
    } finally {
      setSending(false);
    }
  }

  const entries = report ? [...report.entries].sort((a, b) => (b.holding?.shares > 0) - (a.holding?.shares > 0) || ORDER[a.action] - ORDER[b.action] || Math.abs(b.combined_score) - Math.abs(a.combined_score)) : [];
  const chances = entries.filter((e) => e.action === "Kaufen prüfen" && !(e.holding?.shares > 0)).length;
  const warnings = entries.filter((e) => e.holding?.advice?.level === "bad").length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{greeting()}</h1>
          <p className="muted">
            {report ? (
              <>
                {chances ? `${chances} ${chances === 1 ? "Gelegenheit" : "Gelegenheiten"}` : "Keine neue Gelegenheit"}
                {warnings ? ` · ${warnings} ${warnings === 1 ? "Warnung" : "Warnungen"} im Depot` : ""}
                {report.profile && <> · Strategie <Link to="/settings">{report.profile}</Link></>}
              </>
            ) : "Deine Werte auf einen Blick"}
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={!report && !error}>Aktualisieren</button>
          <button className="btn primary" onClick={send} disabled={sending || !report?.entries.length}>{sending ? "Sende …" : "Aufs Handy schicken"}</button>
        </div>
      </div>
      {msg && <p className="note" role="status">{msg}</p>}

      <Onboarding settings={settings} count={report?.entries.length ?? 1} />
      <DepotStrip data={depot} />

      <ErrorText error={error} />
      {!report && !error && <Loading text="Schaue mir deine Werte und die Nachrichten an …" />}

      {report && !report.entries.length && !Object.keys(report.errors).length && (
        <div className="empty hero-empty">
          <h3>Noch keine Werte</h3>
          <p className="muted">Such oben nach einer Aktie oder einem ETF, zum Beispiel „Apple“ oder „MSCI World“. Auf der Seite des Werts tippst du auf „Beobachten“.</p>
        </div>
      )}

      <div className="card-grid">
        {entries.map((e) => <StockCard key={e.symbol} e={e} pro={mode === "pro"} />)}
      </div>
      {report && Object.entries(report.errors).map(([sym, err]) => <p key={sym} className="error small">{sym}: {err}</p>)}

      {log.length > 0 && (
        <>
          <h2 className="section-title">Letzte Alarme</h2>
          <ul className="log-list">
            {log.map((l) => <li key={l.id}><span className="muted small">{dateTime(l.triggered_at)}</span> <strong>{l.symbol}</strong> {l.message}</li>)}
          </ul>
        </>
      )}
    </>
  );
}
