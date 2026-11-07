import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import NewsList from "../components/NewsList.jsx";
import ReportModal from "../components/ReportModal.jsx";
import AssetRow, { actionHint, heldNums, priceNums } from "../components/AssetRow.jsx";
import { ErrorText, Loading } from "../components/ui.jsx";
import { dateTime, money, num, pct, signed, signedMoney, tone } from "../fmt.js";
import { useLiveQuotes } from "../live.js";
import { useMode } from "../mode.js";
import { displayName, displayTicker, greeting } from "../texts.js";

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

function NewsSection({ hasStocks }) {
  const [mine, setMine] = useState(null);
  const [market, setMarket] = useState(null);
  const [tab, setTab] = useState("mine");

  useEffect(() => {
    let alive = true;
    api.get("/news/market?limit=40").then((r) => alive && setMarket(r)).catch(() => alive && setMarket({ items: [], feeds: [] }));
    if (hasStocks) api.get("/news/watchlist?limit=30").then((r) => alive && setMine(r)).catch(() => alive && setMine({ items: [], sources: [] }));
    return () => { alive = false; };
  }, [hasStocks]);

  const minePanel = hasStocks && (
    <section className={`panel ${tab === "mine" ? "" : "hide-narrow"}`} aria-label="Nachrichten zu deinen Werten">
      <div className="panel-head"><h2>Zu deinen Werten</h2></div>
      {!mine ? <Loading text="Suche Nachrichten …" /> : (
        <NewsList items={mine.items} initial={6} showStock
          empty={mine.sources?.length ? "In den letzten Tagen nichts Neues zu deinen Werten." : "Alle Nachrichtenquellen sind ausgeschaltet (Einstellungen → Nachrichten)."} />
      )}
    </section>
  );
  const marketPanel = (
    <section className={`panel ${!hasStocks || tab === "market" ? "" : "hide-narrow"}`} aria-label="Marktnachrichten">
      <div className="panel-head"><h2>Markt &amp; Wirtschaft</h2><Link className="link small" to="/settings#news">Quellen</Link></div>
      {!market ? <Loading text="Lade Marktnachrichten …" /> : (
        <NewsList items={market.items} initial={6} empty="Keine Marktnachrichten. Quellen lassen sich in den Einstellungen eintragen." />
      )}
    </section>
  );
  return (
    <>
      <div className="section-head">
        <h2 className="section-title">Nachrichten</h2>
        {hasStocks && (
          <div className="seg show-narrow" role="tablist">
            <button className={tab === "mine" ? "on" : ""} role="tab" aria-selected={tab === "mine"} onClick={() => setTab("mine")}>Deine Werte</button>
            <button className={tab === "market" ? "on" : ""} role="tab" aria-selected={tab === "market"} onClick={() => setTab("market")}>Markt</button>
          </div>
        )}
      </div>
      <div className={`news-grid ${hasStocks ? "" : "single"}`}>
        {minePanel}
        {marketPanel}
      </div>
    </>
  );
}

function SummaryTiles({ depot, shadow }) {
  const t = depot?.totals;
  const hasDepot = depot?.items?.some((p) => !p.closed);
  if (!hasDepot && !shadow?.started) return null;
  return (
    <div className="summary-tiles">
      {hasDepot && (
        <Link to="/depot" className="summary-tile">
          <span className="muted small">Mein Depot</span>
          <strong>{money(t.value, t.currency)}</strong>
          <span className={`small ${tone(t.pl)}`}>{signedMoney(t.pl, t.currency)} · {pct(t.pl_pct, 1)}</span>
        </Link>
      )}
      {shadow?.started && (
        <Link to="/depot/schatten" className="summary-tile">
          <span className="muted small">Schattendepot</span>
          <strong>{money(shadow.value, shadow.currency)}</strong>
          <span className={`small ${tone(shadow.pl)}`}>{signedMoney(shadow.pl, shadow.currency)} · {pct(shadow.pl_pct, 1)}</span>
        </Link>
      )}
    </div>
  );
}

function rowFor(e, q, pro) {
  const live = q && q.currency === e.currency ? q : null;
  const price = live ? live.price : e.analysis.last_close;
  const change = live && live.change_pct != null ? live.change_pct : e.analysis.change_pct_1d;
  const h = e.holding?.shares > 0 ? e.holding : null;
  const hv = h && live && h.invested && h.currency === e.currency
    ? { ...h, value: h.shares * price, pl: h.shares * price - h.invested, pl_pct: (h.shares * price / h.invested - 1) * 100 } : h;
  const nums = hv ? heldNums(hv, e.currency) : priceNums(price, change, e.currency);
  const meta = hv
    ? <>{num(h.shares, h.shares % 1 ? 3 : 0)} Stück · <span className={tone(change)}>{pct(change)} heute</span></>
    : <>{displayTicker(e)}{pro ? ` · Score ${signed(e.combined_score)}` : ""}</>;
  let hint = h ? actionHint(h.advice) : null;
  if (!h && e.action === "Kaufen prüfen") hint = { level: "good", text: e.reasons[0] };
  if (!h && e.action === "Reduzieren prüfen") hint = { level: "warn", text: e.reasons[0] };
  return { meta, nums, hint, held: !!h };
}

export default function Home() {
  const { mode } = useMode();
  const [report, setReport] = useState(null);
  const [log, setLog] = useState([]);
  const [settings, setSettings] = useState(null);
  const [depot, setDepot] = useState(null);
  const [shadow, setShadow] = useState(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [params, setParams] = useSearchParams();
  const [showReport, setShowReport] = useState(() => params.get("bericht"));
  const closeReport = () => {
    setShowReport(null);
    if (params.get("bericht")) { params.delete("bericht"); setParams(params, { replace: true }); }
  };

  const load = useCallback(async () => {
    setError("");
    setReport(null);
    api.get("/settings").then(setSettings).catch(() => {});
    api.get("/positions").then(setDepot).catch(() => {});
    api.get("/paper").then(setShadow).catch(() => {});
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
      setMsg("Bericht verschickt. Antippen der Nachricht öffnet ihn hier.");
    } catch (e) {
      setMsg(e.message);
    } finally {
      setSending(false);
    }
  }

  const quotes = useLiveQuotes(report ? report.entries.map((x) => x.symbol) : []);
  const pro = mode === "pro";
  const entries = report ? [...report.entries].sort((a, b) => ORDER[a.action] - ORDER[b.action]
    || (b.holding?.shares > 0) - (a.holding?.shares > 0) || Math.abs(b.combined_score) - Math.abs(a.combined_score)) : [];
  const rows = entries.map((e) => ({ e, ...rowFor(e, quotes[e.symbol], pro) }));
  const important = rows.filter((r) => r.hint);
  const rest = rows.filter((r) => !r.hint);
  const restShown = showAll ? rest : rest.slice(0, 6);
  const chances = entries.filter((e) => e.action === "Kaufen prüfen" && !(e.holding?.shares > 0)).length;
  const warnings = entries.filter((e) => e.holding?.advice?.level === "bad").length;
  const renderRow = (r) => (
    <AssetRow key={r.e.symbol} symbol={r.e.symbol} name={displayName(r.e)} meta={r.meta} action={r.e.action} held={r.held}
      top={r.nums.top} bottom={r.nums.bottom} hint={r.hint} />
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{greeting()}</h1>
          <p className="muted home-sub">
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
          <button className="btn hide-sm" onClick={load} disabled={!report && !error}>Aktualisieren</button>
          <button className="btn" onClick={() => setShowReport("latest")}>Bericht</button>
          <button className="btn primary" onClick={send} disabled={sending || !report?.entries.length}>{sending ? "Sende …" : "Aufs Handy"}</button>
        </div>
      </div>
      {msg && <p className="note" role="status">{msg}</p>}
      {showReport && <ReportModal id={showReport === "latest" ? null : showReport} onClose={closeReport} />}

      <Onboarding settings={settings} count={report?.entries.length ?? 1} />
      <SummaryTiles depot={depot} shadow={shadow} />

      <ErrorText error={error} />
      {!report && !error && <Loading text="Schaue mir deine Werte und die Nachrichten an …" />}

      {report && !report.entries.length && !Object.keys(report.errors).length && (
        <div className="empty hero-empty">
          <h3>Noch keine Werte</h3>
          <p className="muted">Such oben nach einer Aktie oder einem ETF, zum Beispiel „Apple“ oder „MSCI World“. Auf der Seite des Werts tippst du auf „Beobachten“.</p>
        </div>
      )}

      {report && report.entries.length > 0 && (
        <>
          <div className="list-head"><h2>Heute wichtig</h2>{important.length > 0 && <span className="muted small">{important.length}</span>}</div>
          {important.length ? <ul className="asset-list">{important.map(renderRow)}</ul>
            : <p className="calm-note">Alles ruhig – bei keinem deiner Werte ist gerade etwas zu tun.</p>}
          {rest.length > 0 && (
            <>
              <div className="list-head"><h2>Alle weiteren Werte</h2><Link className="small" to="/watchlist">Meine Werte →</Link></div>
              <ul className="asset-list">
                {restShown.map(renderRow)}
                {rest.length > restShown.length && (
                  <li><button className="list-more" onClick={() => setShowAll(true)}>Alle {rest.length} anzeigen</button></li>
                )}
              </ul>
            </>
          )}
        </>
      )}
      {report && Object.entries(report.errors).map(([sym, err]) => <p key={sym} className="error small">{sym}: {err}</p>)}

      {report && <NewsSection hasStocks={report.entries.length > 0} />}

      {log.length > 0 && (
        <>
          <h2 className="section-title">Letzte Alarme</h2>
          <ul className="log-list">
            {log.slice(0, 3).map((l) => (
              <li key={l.id}>
                <span className="muted small">{dateTime(l.triggered_at)}</span>{" "}
                <Link to={`/chart/${encodeURIComponent(l.symbol)}`}><strong>{displayName(l)}</strong></Link> {l.message}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
