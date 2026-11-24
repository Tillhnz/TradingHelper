import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useCachedGet } from "../cache.js";
import AssetRow, { actionHint, priceNums } from "../components/AssetRow.jsx";
import Icon from "../components/Icon.jsx";
import NewsList from "../components/NewsList.jsx";
import { Loading } from "../components/ui.jsx";
import { DriverBar, Gauge, LineArea, ProbBar, Spark, Stack } from "../components/viz.jsx";
import { dateTime, money, num, pct, signedMoney, tone } from "../fmt.js";
import { useLiveQuotes } from "../live.js";
import { SORT_LABEL, sortAssets, sortFrom } from "../assetSort.js";
import Freshness, { latestTime } from "../components/Freshness.jsx";
import { ACTION_UI, displayName, displayTicker, greeting } from "../texts.js";

/* Jeder Baustein bekommt { shared, config, size, priv } – shared enthält die gemeinsam geladenen Daten
   (Übersicht der Werte, Portfolio), damit nicht jeder Baustein dasselbe lädt. */

function Card({ title, icon, link, linkLabel = "Mehr", children, foot, bare = false }) {
  return (
    <section className={`wcard ${bare ? "bare" : ""}`}>
      {title && (
        <header className="whead">
          <h2 className="wtitle">{icon && <Icon name={icon} />}{title}</h2>
          {link && <Link to={link}>{linkLabel} <Icon name="chev" /></Link>}
        </header>
      )}
      <div className="wbody">{children}</div>
      {foot && <div className="wfoot">{foot}</div>}
    </section>
  );
}

const hide = (priv, text) => (priv ? "•••" : text);

// ---------- Begrüßung ----------
function GreetingW({ shared, user }) {
  const rows = shared.rows || [];
  const pf = shared.portfolio;
  const attention = rows.filter((r) => r.action === "Reduzieren prüfen" || r.holding?.advice?.level === "bad"
    || r.model?.action === "Reduzieren prüfen").length;
  const chances = rows.filter((r) => r.action === "Kaufen prüfen" && !r.holding).length;
  const parts = [];
  if (pf?.value) parts.push(<span key="v">Vermögen <strong>{hide(shared.priv, money(pf.value, pf.currency))}</strong>{pf.day_change_pct != null && <> · <span className={`delta ${tone(pf.day_change_pct)}`}>{pct(pf.day_change_pct)}</span> heute</>}</span>);
  if (attention) parts.push(<span key="a">{attention} {attention === 1 ? "Wert braucht" : "Werte brauchen"} Aufmerksamkeit</span>);
  if (chances) parts.push(<span key="c">{chances} {chances === 1 ? "Gelegenheit" : "Gelegenheiten"}</span>);
  if (!parts.length && rows.length) parts.push(<span key="r">Alles ruhig bei deinen {rows.length} Werten</span>);
  return (
    <div className="wcard bare">
      <h1 className="home-greet">{greeting()}{user?.username ? `, ${user.username}` : ""}</h1>
      <p className="home-sub">{parts.length ? parts.reduce((acc, p, i) => (i ? [...acc, " · ", p] : [p]), []) : "Deine Werte, Depots und der Markt auf einen Blick."}</p>
    </div>
  );
}

// ---------- Vermögen ----------
function PrivToggle({ priv, onToggle }) {
  if (!onToggle) return null;
  return (
    <button className="icon-btn priv-toggle" onClick={onToggle} aria-pressed={priv}
      title={priv ? "Beträge anzeigen" : "Beträge verbergen (z. B. unterwegs)"} aria-label={priv ? "Beträge anzeigen" : "Beträge verbergen"}>
      <Icon name="eye" />{priv && <span className="priv-strike" aria-hidden="true" />}
    </button>
  );
}

function PortfolioW({ shared, size }) {
  const pf = shared.portfolio;
  const priv = shared.priv;
  if (!pf) return <Card title="Vermögen" icon="wallet" link="/portfolio"><Loading text="Rechne alle Depots zusammen …" /></Card>;
  if (!pf.lines?.length) {
    return (
      <Card title="Vermögen" icon="wallet" link="/portfolio" linkLabel="Depot hinzufügen">
        <p className="wempty">Noch keine Bestände. Lade Umsätze (CSV) oder Abrechnungen (PDF) von Consorsbank, Commerzbank oder finanzen.net zero hoch – oder erfasse Käufe.</p>
      </Card>
    );
  }
  const hist = (pf.history || []).map((h) => h.value);
  const nAcc = pf.accounts?.length || 0;
  const manual = pf.lines.some((x) => x.source === "manual");
  const where = nAcc ? `${nAcc} ${nAcc === 1 ? "Depot" : "Depots"}${manual ? " + manuelle Käufe" : ""}` : "manuell erfasst";
  const foot = (
    <span className="foot-split">
      <span>{where} · {pf.lines.length} {pf.lines.length === 1 ? "Position" : "Positionen"}</span>
      <Freshness asOf={pf.as_of} oldest={pf.oldest} delay={pf.delay_min} at={pf.as_of ? null : shared.portfolioAt} />
    </span>
  );
  return (
    <Card title="Vermögen" icon="wallet" link="/portfolio" linkLabel="Portfolio" foot={foot}>
      <div className="kpi-row">
        <div>
          <div className="kpi kpi-with-toggle">{hide(priv, money(pf.value, pf.currency))}<PrivToggle priv={priv} onToggle={shared.togglePriv} /></div>
          <div className="kpi-sub">
            {pf.day_change_pct != null && <span className={`delta ${tone(pf.day_change_pct)}`}>{priv ? "" : `${signedMoney(pf.day_change, pf.currency)} · `}{pct(pf.day_change_pct)} heute</span>}
          </div>
        </div>
        {pf.pl_pct != null && (
          <div>
            <span className="kpi-label">seit Kauf</span>
            <span className={`kpi-small ${tone(pf.pl)}`}>{priv ? pct(pf.pl_pct, 1) : signedMoney(pf.pl, pf.currency)}</span>
            {!priv && <span className={`small ${tone(pf.pl)}`}> {pct(pf.pl_pct, 1)}</span>}
          </div>
        )}
      </div>
      {priv && <p className="small muted priv-note">Beträge sind verborgen – Auge antippen, um sie zu zeigen.</p>}
      {size !== "s" && hist.length > 2 && <div style={{ marginTop: "0.75rem" }}><LineArea values={hist} height={90} /></div>}
      {pf.hints?.length > 0 && <p className="small" style={{ margin: "0.6rem 0 0", color: "var(--amber)" }}><Icon name="alert" /> {pf.hints[0].text}</p>}
    </Card>
  );
}

// ---------- Aufteilung ----------
function AllocationW({ shared }) {
  const [by, setBy] = useState("type");
  const pf = shared.portfolio;
  const items = pf?.allocation?.[by] || [];
  return (
    <Card title="Aufteilung" icon="pie" link="/portfolio">
      <div className="seg" style={{ marginBottom: "0.8rem" }}>
        {[["type", "Anlageart"], ["account", "Depot"], ["country", "Land"]].map(([k, l]) => (
          <button key={k} className={by === k ? "on" : ""} onClick={() => setBy(k)}>{l}</button>
        ))}
      </div>
      {!pf ? <Loading /> : items.length ? <Stack items={items} /> : <p className="wempty">Noch keine Bestände.</p>}
    </Card>
  );
}

// ---------- Werte ----------
function ListFoot({ rows, quotes, at, sort }) {
  const t = latestTime(rows, quotes);
  return (
    <span className="foot-split">
      <span>Sortiert: {SORT_LABEL[sort] || "eigene Reihenfolge"} · <Link to="/watchlist">ändern</Link></span>
      <Freshness asOf={t.asOf} delay={t.delay} dayOnly={t.dayOnly} at={t.asOf ? null : at} />
    </span>
  );
}

function rowHint(r) {
  const h = r.holding;
  let hint = h ? actionHint(h.advice) : null;
  if (!hint && r.model?.action === "Reduzieren prüfen" && r.model.weight > 0) {
    hint = { level: h ? "bad" : "warn", text: `Modell: ${Math.round(r.model.p_down * 100)} % Wahrscheinlichkeit für einen Rückgang in ${r.model.days || 20} Tagen` };
  }
  if (!hint && !h && r.action === "Kaufen prüfen") hint = { level: "good", text: r.entry || "Gute Gelegenheit laut Regeln" };
  if (!hint && r.action === "Reduzieren prüfen") hint = { level: "warn", text: "Die Signale sind überwiegend negativ" };
  return hint;
}

function Rows({ rows, quotes, limit, withHints = false }) {
  return (
    <ul className="asset-list" style={{ border: 0, boxShadow: "none", background: "transparent" }}>
      {rows.slice(0, limit).map((r, i) => {
        const q = quotes[r.symbol];
        const live = q && q.currency === r.currency ? q : null;
        const nums = priceNums(live ? live.price : r.price, live?.change_pct ?? r.change_pct, r.currency);
        const meta = <>{r.holding && <span className="held-mark" title="Im Depot"><Icon name="briefcase" /></span>}{displayTicker(r)}
          {r.model && r.model.weight > 0 && <span className={`model-chip ${ACTION_UI[r.model.action]?.tone || ""}`} title="Einschätzung des Modells"><Icon name="brain" />{ACTION_UI[r.model.action]?.short}</span>}</>;
        return (
          <AssetRow key={r.symbol} symbol={r.symbol} name={displayName(r)} meta={meta} action={r.action} held={!!r.holding}
            top={r.pending ? { text: "lädt …" } : nums.top} bottom={r.pending ? null : nums.bottom} error={r.error && !r.pending}
            hint={withHints ? rowHint(r) : null} bo={r.breakout} index={i} />
        );
      })}
    </ul>
  );
}

function TodayW({ shared }) {
  const rows = shared.rows;
  const quotes = useLiveQuotes((rows || []).map((r) => r.symbol));
  if (!rows) return <Card title="Heute wichtig" icon="zap"><Loading /></Card>;
  const { sort, order } = sortFrom(shared.settings);
  const important = sortAssets(rows.filter((r) => rowHint(r)), sort, order, quotes);
  return (
    <Card title="Heute wichtig" icon="zap" link="/watchlist" linkLabel="Alle Werte"
      foot={<ListFoot rows={rows} quotes={quotes} at={shared.rowsAt} sort={sort} />}>
      {important.length ? <Rows rows={important} quotes={quotes} limit={6} withHints />
        : <p className="calm-note" style={{ margin: 0 }}><Icon name="check" /> Alles ruhig – bei keinem deiner Werte ist gerade etwas zu tun.</p>}
    </Card>
  );
}

function WatchlistW({ shared, size }) {
  const rows = shared.rows;
  const [all, setAll] = useState(false);
  const quotes = useLiveQuotes((rows || []).map((r) => r.symbol));
  if (!rows) return <Card title="Meine Werte" icon="star"><Loading /></Card>;
  if (!rows.length) return <Card title="Meine Werte" icon="star"><p className="wempty">Such oben nach einer Aktie oder einem ETF und tippe auf „Beobachten“.</p></Card>;
  const limit = all ? rows.length : size === "xl" ? 10 : 6;
  const { sort, order } = sortFrom(shared.settings);
  return (
    <Card title="Meine Werte" icon="star" link="/watchlist" linkLabel="Verwalten"
      foot={<ListFoot rows={rows} quotes={quotes} at={shared.rowsAt} sort={sort} />}>
      <Rows rows={sortAssets(rows, sort, order, quotes)} quotes={quotes} limit={limit} />
      {rows.length > limit && <button className="list-more" onClick={() => setAll(true)}>Alle {rows.length} anzeigen</button>}
    </Card>
  );
}

function MoversW({ shared }) {
  const rows = (shared.rows || []).filter((r) => r.change_pct != null);
  const sorted = [...rows].sort((a, b) => b.change_pct - a.change_pct);
  const up = sorted.slice(0, 3);
  const down = sorted.slice(-3).reverse().filter((r) => !up.includes(r));
  const item = (r) => (
    <li key={r.symbol}>
      <Link to={`/chart/${encodeURIComponent(r.symbol)}`} className="two"><span className="nm">{displayName(r)}</span><span className="sub">{money(r.price, r.currency)}</span></Link>
      <span className={`rt delta ${tone(r.change_pct)}`}>{pct(r.change_pct)}</span>
    </li>
  );
  return (
    <Card title="Gewinner & Verlierer" icon="up" foot={shared.rows ? <Freshness {...latestTime(shared.rows)} at={shared.rowsAt} /> : null}>
      {!shared.rows ? <Loading /> : rows.length ? <ul className="mini-list">{up.map(item)}{down.map(item)}</ul> : <p className="wempty">Noch keine Kurse.</p>}
    </Card>
  );
}

// ---------- Märkte ----------
function MarketsW({ size }) {
  const q = useCachedGet("/markets");
  const items = q.data?.items || [];
  const times = items.map((m) => m.time).filter(Boolean);
  const foot = times.length ? <Freshness asOf={Math.max(...times)} prefix="Kurse" /> : q.at ? <Freshness at={q.at} /> : null;
  if (size === "s" && q.data) {
    return (
      <Card title="Märkte" icon="globe" link="/markt" foot={foot}>
        <ul className="mini-list">
          {items.filter((m) => m.price != null).map((m) => (
            <li key={m.symbol}>
              <Link to={`/chart/${encodeURIComponent(m.symbol)}`} className="nm">{m.label}</Link>
              <span className="rt"><span className="small">{num(m.price, m.price > 1000 ? 0 : 2)}</span> <span className={`small delta ${tone(m.change_pct)}`}>{pct(m.change_pct, 1)}</span></span>
            </li>
          ))}
        </ul>
      </Card>
    );
  }
  return (
    <Card title="Märkte" icon="globe" link="/markt" foot={foot}>
      {!q.data ? <Loading /> : (
        <div className="mkt-grid">
          {items.filter((m) => m.price != null).map((m) => (
            <Link key={m.symbol} to={`/chart/${encodeURIComponent(m.symbol)}`} className="mkt" style={{ textDecoration: "none", color: "inherit" }}>
              <span className="lbl">{m.label}</span>
              <span className="val">{num(m.price, m.price > 1000 ? 0 : 2)}</span>
              <span className={`small delta ${tone(m.change_pct)}`}>{pct(m.change_pct)}</span>
              <Spark values={m.spark} height={22} />
            </Link>
          ))}
          {!items.some((m) => m.price != null) && <p className="wempty">Kurse kommen in Kürze – der Hintergrunddienst lädt sie gerade.</p>}
        </div>
      )}
    </Card>
  );
}

// ---------- Konjunktur ----------
const unit = (u) => (u === "%" ? " %" : u === "%-Pkt." ? " Pkt." : u === "Tsd." ? "" : "");
export function fmtMacro(i) {
  if (i.value == null) return "–";
  const v = i.unit === "Tsd." ? num(i.value / 1000, 0) + " Tsd." : num(i.value, Math.abs(i.value) >= 100 ? 1 : 2) + unit(i.unit);
  return v;
}
export function MacroList({ items, limit }) {
  return (
    <ul className="macro-list">
      {items.slice(0, limit).map((i) => (
        <li key={i.id}>
          <span className="nm"><span>{i.label}</span><span>{i.region} · {i.source} · {dateTime(i.as_of).split(",")[0]}</span></span>
          <span className="val">{fmtMacro(i)}</span>
          <span className={`chg tone-${i.tone}`}>{i.change == null ? "" : `${i.change > 0 ? "▲" : i.change < 0 ? "▼" : "•"} ${num(Math.abs(i.change), 2)}`}</span>
        </li>
      ))}
    </ul>
  );
}
export function Regime({ r }) {
  if (!r) return null;
  const on = (g, f) => (r.growth_up === g && r.inflation_up === f ? "on" : "");
  return (
    <div className="regime" style={{ display: "flex", gap: "0.9rem", alignItems: "center" }}>
      <div className="regime-quad" aria-hidden="true" title="oben: Wachstum steigt · links: Inflation steigt">
        <span className={on(true, true)} /><span className={on(true, false)} />
        <span className={on(false, true)} /><span className={on(false, false)} />
      </div>
      <div><strong>{r.title}</strong><span className="muted small">{r.text}</span></div>
    </div>
  );
}
function MacroW({ size }) {
  const q = useCachedGet("/macro");
  const d = q.data;
  const pick = ["ecb_rate", "ea_inflation", "de_inflation", "us_rate", "us_inflation", "de_unemployment", "ea_sentiment", "us_curve"];
  const items = (d?.indicators || []).filter((i) => pick.includes(i.id)).sort((a, b) => pick.indexOf(a.id) - pick.indexOf(b.id));
  return (
    <Card title="Konjunktur" icon="building" link="/markt">
      {!d ? <Loading /> : (
        <>
          <Regime r={d.regime} />
          {items.length ? <div style={{ marginTop: "0.6rem" }}><MacroList items={items} limit={size === "s" ? 4 : 8} /></div>
            : <p className="wempty">Die Konjunkturzahlen werden gerade zum ersten Mal geladen.</p>}
        </>
      )}
    </Card>
  );
}

// ---------- Stimmung ----------
function MoodW() {
  const q = useCachedGet("/mood");
  const d = q.data;
  const fg = d?.fear_greed;
  return (
    <Card title="Stimmung" icon="gauge" link="/markt">
      {!d ? <Loading /> : (
        <>
          {fg ? <Gauge value={fg.score} label={fg.label} sub={fg.previous_week != null ? `vor einer Woche ${Math.round(fg.previous_week)}` : "CNN Fear & Greed"} />
            : <p className="wempty">Marktstimmung wird geladen.</p>}
          {d.social != null && (
            <p className="small" style={{ margin: "0.6rem 0 0" }}>Netz-Stimmung zu deinen Werten:{" "}
              <strong className={tone(d.social)}>{d.social > 0.15 ? "positiv" : d.social < -0.15 ? "negativ" : "neutral"}</strong> ({num(d.social, 2)})</p>
          )}
          {d.loud?.length > 0 && <p className="small muted" style={{ margin: "0.3rem 0 0" }}>Viel Aufmerksamkeit: {d.loud.map((x) => x.name || x.symbol).join(", ")}</p>}
        </>
      )}
    </Card>
  );
}

// ---------- Modell ----------
function ModelW({ shared, user }) {
  const st = useCachedGet("/model");
  const rows = (shared.rows || []).filter((r) => r.model);
  const sorted = [...rows].sort((a, b) => Math.abs(b.model.expected) - Math.abs(a.model.expected));
  const hz = st.data?.horizons || {};
  const any = Object.values(hz)[0];
  const [msg, setMsg] = useState("");
  async function train() {
    try { await api.post("/model/train"); setMsg("Lernt jetzt – dauert einige Minuten."); } catch (e) { setMsg(e.message); }
  }
  return (
    <Card title="Modell" icon="brain" link="/modell" linkLabel="Details"
      foot={any ? `Gewicht neben den Regeln: ${Math.round((any.weight || 0) * 100)} % · gelernt bis ${dateTime(any.to).split(",")[0]}` : null}>
      {!st.data ? <Loading /> : !any ? (
        <>
          <p className="wempty">Das Modell hat noch nicht gelernt. Der erste Lauf passiert heute Nacht automatisch.</p>
          {user?.is_admin && <div className="actions"><button className="btn" onClick={train}><Icon name="brain" /> Jetzt lernen</button></div>}
          {msg && <p className="small muted">{msg}</p>}
        </>
      ) : sorted.length ? (
        <ul className="mini-list">
          {sorted.slice(0, 5).map((r) => (
            <li key={r.symbol} style={{ gridTemplateColumns: "minmax(0,1fr) 46%" }}>
              <Link to={`/chart/${encodeURIComponent(r.symbol)}`} className="two"><span className="nm">{displayName(r)}</span>
                <span className="sub">{ACTION_UI[r.model.action]?.label} · {r.model.days || 20} Tage</span></Link>
              <ProbBar p={r.model} compact />
            </li>
          ))}
        </ul>
      ) : <p className="wempty">Vorhersagen für deine Werte kommen mit dem nächsten Abendlauf.</p>}
    </Card>
  );
}

// ---------- Rückblick ----------
function ReviewW() {
  const q = useCachedGet("/model/decisions?limit=60");
  const items = (q.data?.items || []).filter((d) => d.verdict);
  const ok = items.filter((d) => /^Richtig|^Vertretbar|^Kaum/.test(d.verdict)).length;
  return (
    <Card title="Rückblick: lag das System richtig?" icon="check" link="/modell">
      {!q.data ? <Loading /> : !items.length ? (
        <p className="wempty">Jede Einschätzung wird nach Ablauf ihres Horizonts nachgerechnet: Wäre Verkaufen besser gewesen? Die ersten Urteile gibt es nach einer Woche.</p>
      ) : (
        <>
          <p style={{ margin: "0 0 0.5rem" }}><span className="kpi-small">{Math.round((ok / items.length) * 100)} %</span> <span className="muted small">der letzten {items.length} Einschätzungen lagen richtig</span></p>
          <ul className="verdict-list">
            {items.slice(0, 4).map((d) => {
              const good = /^Richtig|^Vertretbar|^Kaum/.test(d.verdict);
              return (
                <li key={d.id}>
                  <span className={`vmark ${good ? "ok" : "bad"}`} />
                  <span><strong>{d.name || d.symbol.replace(/\.GTX$/, "")}</strong> <span className="muted small">{dateTime(d.day).split(",")[0]}</span></span>
                  <span className={`small ${tone(d.outcome)}`}>{pct((d.outcome || 0) * 100, 1)}</span>
                  <span className="vd">{d.verdict}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Card>
  );
}

// ---------- Nachrichten, Alarme, Schattendepot, Einrichtung ----------
function NewsW({ shared }) {
  const has = (shared.rows || []).length > 0;
  const q = useCachedGet("/news/watchlist?limit=30", { enabled: has });
  return (
    <Card title="Nachrichten zu deinen Werten" icon="news">
      {!has ? <p className="wempty">Sobald du Werte beobachtest, stehen hier ihre Meldungen.</p>
        : !q.data ? <Loading text="Suche Nachrichten …" /> : <NewsList items={q.data.items} initial={5} showStock empty="In den letzten Tagen nichts Neues." />}
    </Card>
  );
}
function MarketNewsW() {
  const q = useCachedGet("/news/market?limit=40");
  return (
    <Card title="Markt & Wirtschaft" icon="activity" link="/settings#news" linkLabel="Quellen">
      {!q.data ? <Loading /> : <NewsList items={q.data.items} initial={5} empty="Keine Marktnachrichten." />}
    </Card>
  );
}
function AlertsW() {
  const q = useCachedGet("/alerts/log?limit=6");
  const log = q.data || [];
  return (
    <Card title="Letzte Alarme" icon="bell" link="/alerts" linkLabel="Alle">
      {!q.data ? <Loading /> : log.length ? (
        <ul className="mini-list">
          {log.slice(0, 5).map((l) => (
            <li key={l.id}><span className="two"><Link to={`/chart/${encodeURIComponent(l.symbol)}`} className="nm">{displayName(l)}</Link><span className="sub">{l.message}</span></span>
              <span className="rt muted small">{dateTime(l.triggered_at)}</span></li>
          ))}
        </ul>
      ) : <p className="wempty">Noch kein Alarm ausgelöst.</p>}
    </Card>
  );
}
function ShadowW({ shared }) {
  const q = useCachedGet("/paper");
  const s = q.data;
  return (
    <Card title="Schattendepot" icon="flask" link="/depot/schatten">
      {!s ? <Loading /> : !s.started ? <p className="wempty">Das Schattendepot handelt die Einschätzungen mit Spielgeld – es startet mit dem nächsten Bericht.</p> : (
        <div className="kpi-row">
          <div><div className="kpi-small">{hide(shared.priv, money(s.value, s.currency))}</div><span className={`small ${tone(s.pl)}`}>{shared.priv ? "" : signedMoney(s.pl, s.currency)} {pct(s.pl_pct, 1)} seit Start</span></div>
        </div>
      )}
    </Card>
  );
}
function SetupW({ shared }) {
  const s = shared.settings;
  const [hidden, setHidden] = useState(() => { try { return localStorage.getItem("tradehelper_onboarding_done") === "1"; } catch { return false; } });
  if (!s || hidden) return null;
  const steps = [
    { done: (shared.rows || []).length > 0, title: "Werte hinzufügen", to: "/watchlist" },
    { done: (shared.portfolio?.lines || []).length > 0, title: "Depot hochladen", to: "/portfolio" },
    { done: s.fields.ntfy_topic?.value, title: "Push aufs Handy", to: "/settings#notify" },
    { done: s.fields.invest_horizon?.from_ui, title: "Strategie festlegen", to: "/settings#strategy" },
  ];
  const open = steps.filter((x) => !x.done);
  if (!open.length) return null;
  return (
    <div className="onboard-line">
      <span className="muted small">Noch {open.length} {open.length === 1 ? "Schritt" : "Schritte"}:</span>
      {open.map((x) => <Link key={x.title} to={x.to} className="onboard-chip">{x.title} →</Link>)}
      <button className="link small" onClick={() => { try { localStorage.setItem("tradehelper_onboarding_done", "1"); } catch { /* egal */ } setHidden(true); }} aria-label="Ausblenden">✕</button>
    </div>
  );
}

// ---------- Mini-Chart eines Werts ----------
function ChartW({ config }) {
  const sym = config?.symbol;
  const period = config?.period || "6mo";
  const q = useCachedGet(sym ? `/history/${encodeURIComponent(sym)}?period=${period}&interval=1d` : null, { enabled: !!sym });
  const d = q.data;
  const closes = (d?.rows || []).map((r) => r.close);
  const last = closes[closes.length - 1];
  const first = closes[0];
  return (
    <Card title={d?.name || sym || "Mini-Chart"} icon="activity" link={sym ? `/chart/${encodeURIComponent(sym)}` : null} linkLabel="Chart">
      {!sym ? <p className="wempty">Kein Wert gewählt.</p> : !d ? <Loading /> : (
        <>
          <div className="kpi-sub" style={{ marginBottom: "0.4rem" }}>
            <strong className="kpi-small">{money(last, d.currency)}</strong>
            {first && <span className={`delta ${tone(last / first - 1)}`}>{pct((last / first - 1) * 100, 1)}</span>}
            <span className="muted small">{{ "1mo": "1 Monat", "3mo": "3 Monate", "6mo": "6 Monate", "1y": "1 Jahr", "5y": "5 Jahre" }[period]}</span>
          </div>
          <LineArea values={closes} height={110} />
        </>
      )}
    </Card>
  );
}

export const WIDGETS = {
  greeting: { label: "Begrüßung & Lage", icon: "sparkles", text: "Was heute wichtig ist, in einem Satz", sizes: ["l", "xl"], C: GreetingW, bare: true },
  portfolio: { label: "Vermögen", icon: "wallet", text: "Gesamtwert aller Depots mit Verlauf", sizes: ["s", "m", "l", "xl"], C: PortfolioW },
  allocation: { label: "Aufteilung", icon: "pie", text: "Nach Anlageart, Depot oder Land", sizes: ["s", "m", "l"], C: AllocationW },
  today: { label: "Heute wichtig", icon: "zap", text: "Werte, bei denen etwas zu tun ist", sizes: ["m", "l", "xl"], C: TodayW },
  watchlist: { label: "Meine Werte", icon: "star", text: "Kurse und Einschätzung aller Werte", sizes: ["m", "l", "xl"], C: WatchlistW },
  movers: { label: "Gewinner & Verlierer", icon: "up", text: "Größte Tagesbewegungen deiner Werte", sizes: ["s", "m"], C: MoversW },
  markets: { label: "Märkte", icon: "globe", text: "DAX, S&P 500, Gold, Öl, Bitcoin …", sizes: ["s", "m", "l", "xl"], C: MarketsW },
  macro: { label: "Konjunktur", icon: "building", text: "Zinsen, Inflation, Stimmung, Arbeitsmarkt", sizes: ["s", "m", "l"], C: MacroW },
  mood: { label: "Stimmung", icon: "gauge", text: "Fear & Greed und soziale Netzwerke", sizes: ["s", "m"], C: MoodW },
  model: { label: "Modell", icon: "brain", text: "Was das lernende Modell gerade sieht", sizes: ["m", "l", "xl"], C: ModelW },
  review: { label: "Rückblick", icon: "check", text: "Lag das System richtig? Halten oder Verkaufen?", sizes: ["s", "m", "l"], C: ReviewW },
  news: { label: "Nachrichten zu deinen Werten", icon: "news", text: "Neueste Meldungen mit Stimmung", sizes: ["m", "l", "xl"], C: NewsW },
  market_news: { label: "Markt & Wirtschaft", icon: "activity", text: "Allgemeine Wirtschaftsnachrichten", sizes: ["m", "l", "xl"], C: MarketNewsW },
  alerts: { label: "Letzte Alarme", icon: "bell", text: "Zuletzt ausgelöste Alarme", sizes: ["s", "m"], C: AlertsW },
  shadow: { label: "Schattendepot", icon: "flask", text: "Spielgeld-Depot, das die Einschätzungen handelt", sizes: ["s", "m"], C: ShadowW },
  setup: { label: "Einrichtung", icon: "sparkles", text: "Was zum Start noch fehlt", sizes: ["xl"], C: SetupW, bare: true },
  chart: { label: "Mini-Chart", icon: "activity", text: "Kursverlauf eines Werts deiner Wahl", sizes: ["s", "m", "l"], C: ChartW, multi: true },
};

export const DEFAULT_WIDGETS = [
  ["setup", "xl"], ["greeting", "xl"], ["portfolio", "l"], ["markets", "s"], ["today", "l"], ["mood", "s"],
  ["watchlist", "xl"], ["model", "m"], ["macro", "m"], ["news", "m"], ["market_news", "m"], ["review", "m"], ["alerts", "m"],
].map(([type, size], i) => ({ id: `d${i}`, type, size }));

const OLD = { setup: ["setup", "xl"], tiles: ["portfolio", "l"], important: ["today", "xl"], assets: ["watchlist", "xl"], news: ["news", "m"], alerts: ["alerts", "m"] };

/** Gespeichertes Layout lesen (auch das alte Format bis 0.20). */
export function parseLayout(raw) {
  try {
    const v = raw ? JSON.parse(raw) : null;
    if (!v) return { widgets: DEFAULT_WIDGETS, private: false };
    if (Array.isArray(v.widgets)) {
      const ws = v.widgets.filter((w) => WIDGETS[w.type]);
      return { widgets: ws.length ? ws : DEFAULT_WIDGETS, private: !!v.private };
    }
    if (Array.isArray(v.order)) {
      const hidden = new Set(v.hidden || []);
      const ws = v.order.filter((k) => OLD[k] && !hidden.has(k)).map((k, i) => ({ id: `o${i}`, type: OLD[k][0], size: OLD[k][1] }));
      return { widgets: [...ws, ...DEFAULT_WIDGETS.filter((d) => !ws.some((w) => w.type === d.type) && ["markets", "macro", "mood", "model"].includes(d.type))], private: !!v.private };
    }
  } catch { /* Standard */ }
  return { widgets: DEFAULT_WIDGETS, private: false };
}

export { DriverBar };
