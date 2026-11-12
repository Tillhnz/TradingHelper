import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import NewsList from "../components/NewsList.jsx";
import ReportModal from "../components/ReportModal.jsx";
import AssetRow, { actionHint, priceNums } from "../components/AssetRow.jsx";
import Modal from "../components/Modal.jsx";
import { ErrorText, Loading } from "../components/ui.jsx";
import Icon from "../components/Icon.jsx";
import { dateTime, money, pct, signed, signedMoney, tone } from "../fmt.js";
import { useLiveQuotes } from "../live.js";
import { readCache, standLabel, useCachedGet, writeCache } from "../cache.js";
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
  const open = steps.filter((s) => !s.done);
  if (!open.length) return null;
  return (
    <div className="onboard-line">
      <span className="muted small">Noch {open.length} {open.length === 1 ? "Schritt" : "Schritte"} zum Einrichten:</span>
      {open.map((s) => <Link key={s.title} to={s.to} className="onboard-chip" title={s.text}>{s.title} →</Link>)}
      <button className="link small" onClick={() => { try { localStorage.setItem(DISMISS_KEY, "1"); } catch { /* egal */ } setHidden(true); }} aria-label="Ausblenden">✕</button>
    </div>
  );
}

function NewsSection({ hasStocks, refreshKey }) {
  // Zuletzt geladene Nachrichten sofort zeigen, neue kommen im Hintergrund dazu
  const mineQ = useCachedGet("/news/watchlist?limit=30", { enabled: hasStocks });
  const marketQ = useCachedGet("/news/market?limit=40");
  const [tab, setTab] = useState("mine");
  const mine = mineQ.data || (mineQ.error ? { items: [], sources: [] } : null);
  const market = marketQ.data || (marketQ.error ? { items: [], feeds: [] } : null);
  const { reload: reloadMine } = mineQ;
  const { reload: reloadMarket } = marketQ;
  useEffect(() => {
    if (!refreshKey) return;
    reloadMarket();
    if (hasStocks) reloadMine();
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const minePanel = hasStocks && (
    <section className={`panel ${tab === "mine" ? "" : "hide-narrow"}`} aria-label="Nachrichten zu deinen Werten">
      <div className="panel-head"><h2><Icon name="news" className="h-icon" /> Zu deinen Werten</h2></div>
      {!mine ? <Loading text="Suche Nachrichten …" /> : (
        <NewsList items={mine.items} initial={6} showStock
          empty={mine.sources?.length ? "In den letzten Tagen nichts Neues zu deinen Werten." : "Alle Nachrichtenquellen sind ausgeschaltet (Einstellungen → Nachrichten)."} />
      )}
    </section>
  );
  const marketPanel = (
    <section className={`panel ${!hasStocks || tab === "market" ? "" : "hide-narrow"}`} aria-label="Marktnachrichten">
      <div className="panel-head"><h2><Icon name="activity" className="h-icon" /> Markt &amp; Wirtschaft</h2><Link className="link small" to="/settings#news">Quellen</Link></div>
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

function SummaryTiles({ depot, shadow, priv }) {
  const t = depot?.totals;
  const hasDepot = depot?.items?.some((p) => !p.closed);
  if (!hasDepot && !shadow?.started) return null;
  return (
    <div className="summary-tiles">
      {hasDepot && (
        <Link to="/depot" className="summary-tile">
          <span className="muted small"><Icon name="wallet" /> Mein Depot</span>
          <strong className={priv ? tone(Math.round((t.pl_pct || 0) * 10) / 10) : ""}>{priv ? pct(t.pl_pct, 1) : money(t.value, t.currency)}</strong>
          <span className={`small ${priv ? "muted" : tone(t.pl)}`}>{priv ? "seit Kauf" : <>{signedMoney(t.pl, t.currency)} · {pct(t.pl_pct, 1)}</>}</span>
        </Link>
      )}
      {shadow?.started && (
        <Link to="/depot/schatten" className="summary-tile">
          <span className="muted small"><Icon name="flask" /> Schattendepot</span>
          <strong className={priv ? tone(Math.round((shadow.pl_pct || 0) * 10) / 10) : ""}>{priv ? pct(shadow.pl_pct, 1) : money(shadow.value, shadow.currency)}</strong>
          <span className={`small ${priv ? "muted" : tone(shadow.pl)}`}>{priv ? "seit Start" : <>{signedMoney(shadow.pl, shadow.currency)} · {pct(shadow.pl_pct, 1)}</>}</span>
        </Link>
      )}
    </div>
  );
}

export const WIDGETS = {
  setup: { label: "Einrichtungs-Hinweise", icon: "sparkles", text: "Was zum Start noch fehlt" },
  tiles: { label: "Depot & Schattendepot", icon: "wallet", text: "Kacheln mit Gesamtwert und Entwicklung" },
  important: { label: "Heute wichtig", icon: "zap", text: "Werte, bei denen etwas zu tun ist" },
  assets: { label: "Alle weiteren Werte", icon: "list", text: "Restliche Werte mit Kurs" },
  news: { label: "Nachrichten", icon: "news", text: "Zu deinen Werten und zum Markt" },
  alerts: { label: "Letzte Alarme", icon: "bell", text: "Die drei jüngsten ausgelösten Alarme" },
};
const DEFAULT_LAYOUT = { order: Object.keys(WIDGETS), hidden: [], private: false };

export function parseLayout(raw) {
  try {
    const v = raw ? JSON.parse(raw) : {};
    const order = (v.order || []).filter((w) => WIDGETS[w]);
    return { order: [...new Set([...order, ...DEFAULT_LAYOUT.order])], hidden: (v.hidden || []).filter((w) => WIDGETS[w]), private: !!v.private };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

function LayoutEditor({ layout, onClose, onSave }) {
  const [l, setL] = useState(layout);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const move = (i, d) => setL((x) => {
    const o = [...x.order];
    [o[i], o[i + d]] = [o[i + d], o[i]];
    return { ...x, order: o };
  });
  const toggle = (w) => setL((x) => ({ ...x, hidden: x.hidden.includes(w) ? x.hidden.filter((h) => h !== w) : [...x.hidden, w] }));
  async function save() {
    setBusy(true);
    setError("");
    try {
      await onSave(l);
      onClose();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }
  return (
    <Modal title="Startseite anpassen" onClose={onClose}>
      <p className="muted small">Bausteine ein- oder ausschalten und mit den Pfeilen sortieren. Gilt auf allen Geräten.</p>
      <ul className="layout-list">
        {l.order.map((w, i) => (
          <li key={w} className={l.hidden.includes(w) ? "off" : ""}>
            <Icon name={WIDGETS[w].icon} className="layout-icon" />
            <span className="layout-main"><strong>{WIDGETS[w].label}</strong><span className="muted small">{WIDGETS[w].text}</span></span>
            <span className="layout-move">
              <button className="icon-btn" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`${WIDGETS[w].label} nach oben`}><Icon name="chevup" /></button>
              <button className="icon-btn" onClick={() => move(i, 1)} disabled={i === l.order.length - 1} aria-label={`${WIDGETS[w].label} nach unten`}><Icon name="chevdown" /></button>
            </span>
            <label className="switch" title={l.hidden.includes(w) ? "Einblenden" : "Ausblenden"}>
              <input type="checkbox" checked={!l.hidden.includes(w)} onChange={() => toggle(w)} aria-label={`${WIDGETS[w].label} anzeigen`} />
              <span />
            </label>
          </li>
        ))}
      </ul>
      <label className="layout-private">
        <span className="switch"><input type="checkbox" checked={l.private} onChange={(e) => setL((x) => ({ ...x, private: e.target.checked }))} /><span /></span>
        <span><strong><Icon name="eye" /> Beträge verbergen</strong><span className="muted small">Die Kacheln zeigen nur Prozent statt Euro – praktisch, wenn jemand mitschaut.</span></span>
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button className="btn primary" onClick={save} disabled={busy}><Icon name="check" /> Speichern</button>
        <button className="btn" onClick={() => setL(DEFAULT_LAYOUT)}>Standard</button>
        <button className="btn" onClick={onClose}>Abbrechen</button>
      </div>
    </Modal>
  );
}

/** Gleiche Fehler bei vielen Werten nur einmal nennen („onvista bremst gerade“ statt 16 roter Zeilen). */
function ErrorGroups({ errors }) {
  const groups = {};
  for (const [sym, err] of Object.entries(errors || {})) {
    const msg = String(err).replace(/^[A-Z0-9]{12}:\s*/, "");
    (groups[msg] = groups[msg] || []).push(sym.replace(/\.GTX$/, ""));
  }
  return Object.entries(groups).map(([msg, syms]) => (
    <p key={msg} className="error small error-group">
      <Icon name="alert" /> {syms.length > 2 ? <><strong>{syms.length} Werte</strong> ohne aktuelle Daten: {msg}</> : <>{syms.join(", ")}: {msg}</>}
      {syms.length > 2 && /bremst/.test(msg) && <span className="muted"> Das legt sich meist von selbst nach einigen Minuten.</span>}
    </p>
  ));
}

function rowFor(e, q, pro) {
  const live = q && q.currency === e.currency ? q : null;
  const price = live ? live.price : e.analysis.last_close;
  const change = live && live.change_pct != null ? live.change_pct : e.analysis.change_pct_1d;
  const h = e.holding?.shares > 0 ? e.holding : null;
  // Auf der Startseite steht immer der Kurs – dein Vermögen im Wert siehst du erst auf seiner Seite
  const nums = priceNums(price, change, e.currency);
  const meta = <>{h && <span className="held-mark" title="Im Depot"><Icon name="briefcase" /></span>}{displayTicker(e)}{pro ? ` · Score ${signed(e.combined_score)}` : ""}</>;
  let hint = h ? actionHint(h.advice) : null;
  if (!h && e.action === "Kaufen prüfen") hint = { level: "good", text: e.reasons[0] };
  if (!h && e.action === "Reduzieren prüfen") hint = { level: "warn", text: e.reasons[0] };
  const bo = e.analysis?.breakout;
  if (!hint && bo && bo.tilt !== "neutral") {
    hint = bo.tilt === "up"
      ? { level: "good", text: `Ausbruch-Chance erhöht: ${Math.round(bo.up * 100)} % (üblich ${Math.round(bo.base_up * 100)} %)` }
      : { level: h ? "bad" : "warn", text: `Rutsch-Risiko erhöht: ${Math.round(bo.down * 100)} % (üblich ${Math.round(bo.base_down * 100)} %)${h ? " – Stopp prüfen" : ""}` };
  }
  return { meta, nums, hint, held: !!h };
}

export default function Home() {
  const { mode } = useMode();
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState(false);
  const [params, setParams] = useSearchParams();
  const [showReport, setShowReport] = useState(() => params.get("bericht"));
  const closeReport = () => {
    setShowReport(null);
    if (params.get("bericht")) { params.delete("bericht"); setParams(params, { replace: true }); }
  };

  const [fallback, setFallback] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const settingsQ = useCachedGet("/settings");
  const depotQ = useCachedGet("/positions");
  const shadowQ = useCachedGet("/paper");
  const logQ = useCachedGet("/alerts/log?limit=6");
  const settings = settingsQ.data;
  const depot = depotQ.data;
  const shadow = shadowQ.data;
  const log = logQ.data || [];

  // Übersicht: sofort den zuletzt gesehenen Stand, die frische Einschätzung kommt im Hintergrund
  const [rep, setRep] = useState(() => {
    const c = readCache("/report");
    return { data: c ? c.data : null, at: c ? c.at : null, refreshing: true };
  });
  const report = rep.data;
  const hasReport = useRef(!!rep.data);
  hasReport.current = !!report;
  const seq = useRef(0);

  const load = useCallback(async (fresh = false) => {
    const n = ++seq.current;
    setError("");
    setRep((r) => ({ ...r, refreshing: true }));
    if (fresh === true) {
      settingsQ.reload(); depotQ.reload(); shadowQ.reload(); logQ.reload();
      setRefreshKey((k) => k + 1);
    }
    // Noch gar nichts auf diesem Gerät: den letzten Stand vom Server holen, bis die frische Einschätzung fertig ist
    if (!hasReport.current) {
      api.get("/report?cached=1").then((d) => {
        if (n === seq.current && !hasReport.current) {
          hasReport.current = true;
          setRep((r) => (r.data ? r : { ...r, data: { errors: {}, ...d }, at: d.cached_at ? d.cached_at * 1000 : null }));
        }
      }).catch(() => {});
    }
    try {
      const data = await api.get(`/report${fresh === true ? "?fresh=1" : ""}`);
      if (n !== seq.current) return;
      writeCache("/report", data);
      setFallback("");
      setRep({ data, at: Date.now(), refreshing: false });
    } catch (e) {
      if (n !== seq.current) return;
      if (hasReport.current) {
        setRep((r) => ({ ...r, refreshing: false }));
        setFallback(`Aktualisieren klappt gerade nicht (${e.message}) – du siehst den letzten bekannten Stand.`);
        return;
      }
      // Live-Abruf klappt gerade nicht (z. B. Kursquelle gesperrt): den zuletzt verschickten Bericht zeigen
      try {
        const saved = await api.get("/reports/latest");
        setRep({ data: { errors: {}, ...saved }, at: null, refreshing: false });
        setFallback(`Aktuelle Daten gerade nicht abrufbar (${e.message}) – du siehst den Bericht vom ${saved.created}.`);
      } catch {
        setRep((r) => ({ ...r, refreshing: false }));
        setError(e.message);
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
  const chances = entries.filter((e) => e.action === "Kaufen prüfen" && !(e.holding?.shares > 0)).length;
  const warnings = entries.filter((e) => e.holding?.advice?.level === "bad").length;
  const renderRow = (r, i) => (
    <AssetRow key={r.e.symbol} symbol={r.e.symbol} name={displayName(r.e)} meta={r.meta} action={r.e.action} held={r.held}
      top={r.nums.top} bottom={r.nums.bottom} hint={r.hint} bo={r.e.analysis?.breakout} index={i} />
  );

  const layout = parseLayout(settings?.fields?.home_layout?.value);
  async function saveLayout(l) {
    const value = JSON.stringify(l);
    await api.put("/settings", { home_layout: value });
    settingsQ.set((x) => x && { ...x, fields: { ...x.fields, home_layout: { ...(x.fields.home_layout || {}), value } } });
  }
  const hasEntries = report && report.entries.length > 0;
  function widget(w) {
    switch (w) {
      case "setup": return <Onboarding settings={settings} count={report?.entries.length ?? 1} />;
      case "tiles": return <SummaryTiles depot={depot} shadow={shadow} priv={layout.private} />;
      case "important": return hasEntries && (
        <section className="home-block">
          <div className="list-head"><h2><Icon name="zap" className="h-icon" /> Heute wichtig</h2>{important.length > 0 && <span className="muted small">{important.length}</span>}</div>
          {important.length ? <ul className="asset-list">{important.map(renderRow)}</ul>
            : <p className="calm-note"><Icon name="check" /> Alles ruhig – bei keinem deiner Werte ist gerade etwas zu tun.</p>}
        </section>
      );
      case "assets": {
        const list = layout.hidden.includes("important") ? rows : rest;
        const shown = showAll ? list : list.slice(0, 6);
        return hasEntries && list.length > 0 && (
          <section className="home-block">
            <div className="list-head"><h2><Icon name="list" className="h-icon" /> {layout.hidden.includes("important") ? "Deine Werte" : "Alle weiteren Werte"}</h2><Link className="small more-link" to="/watchlist">Meine Werte <Icon name="arrow" /></Link></div>
            <ul className="asset-list">
              {shown.map(renderRow)}
              {list.length > shown.length && (
                <li><button className="list-more" onClick={() => setShowAll(true)}>Alle {list.length} anzeigen</button></li>
              )}
            </ul>
          </section>
        );
      }
      case "news": return report && <NewsSection hasStocks={report.entries.length > 0} refreshKey={refreshKey} />;
      case "alerts": return log.length > 0 && (
        <section className="home-block">
          <div className="list-head"><h2><Icon name="bell" className="h-icon" /> Letzte Alarme</h2><Link className="small more-link" to="/alerts">Alle <Icon name="arrow" /></Link></div>
          <ul className="log-list">
            {log.slice(0, 3).map((l) => (
              <li key={l.id}>
                <span className="muted small">{dateTime(l.triggered_at)}</span>{" "}
                <Link to={`/chart/${encodeURIComponent(l.symbol)}`}><strong>{displayName(l)}</strong></Link> {l.message}
              </li>
            ))}
          </ul>
        </section>
      );
      default: return null;
    }
  }

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
            {report && (rep.refreshing
              ? <span className="refresh-state"><span className="spinner" aria-hidden="true" /> aktualisiere …</span>
              : rep.at && <span className="refresh-state">{standLabel(rep.at)}</span>)}
          </p>
        </div>
        <div className="actions">
          <button className="btn hide-sm" onClick={() => load(true)} disabled={rep.refreshing}><Icon name="refresh" /> Aktualisieren</button>
          <button className="btn" onClick={() => setShowReport("latest")}><Icon name="report" /> Bericht</button>
          <button className="btn icon-only" onClick={() => setEditing(true)} title="Startseite anpassen" aria-label="Startseite anpassen"><Icon name="sliders" /></button>
          <button className="btn primary" onClick={send} disabled={sending || !report?.entries.length}><Icon name="phone" /> {sending ? "Sende …" : "Aufs Handy"}</button>
        </div>
      </div>
      {msg && <p className="note" role="status">{msg}</p>}
      {showReport && <ReportModal id={showReport === "latest" ? null : showReport} onClose={closeReport} />}
      {editing && <LayoutEditor layout={layout} onClose={() => setEditing(false)} onSave={saveLayout} />}

      <ErrorText error={error} />
      {fallback && <p className="note fallback-note"><Icon name="clock" /> {fallback}</p>}
      {!rep.refreshing && report?.data_status?.paused && (
        <p className="note fallback-note"><Icon name="alert" /> onvista sperrt die Kursabfrage gerade – TradeHelper pausiert noch
          {" "}{Math.ceil(report.data_status.seconds_left / 60)} min und zeigt so lange den letzten bekannten Stand.</p>
      )}
      {!report && !error && <Loading text="Schaue mir deine Werte zum ersten Mal an …" />}

      {report && !report.entries.length && !Object.keys(report.errors).length && (
        <div className="empty hero-empty">
          <h3>Noch keine Werte</h3>
          <p className="muted">Such oben nach einer Aktie oder einem ETF, zum Beispiel „Apple“ oder „MSCI World“. Auf der Seite des Werts tippst du auf „Beobachten“.</p>
        </div>
      )}
      {report && <ErrorGroups errors={report.errors} />}

      {layout.order.filter((w) => !layout.hidden.includes(w)).map((w) => <Fragment key={w}>{widget(w)}</Fragment>)}
    </>
  );
}
