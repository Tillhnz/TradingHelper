import { useState as useStateSafe } from "react";
import { Link } from "react-router-dom";
import { useCachedGet } from "../cache.js";
import { ago } from "./NewsList.jsx";
import Icon from "./Icon.jsx";
import { DriverBar, ProbBar } from "./viz.jsx";
import { num } from "../fmt.js";
import { ACTION_UI } from "../texts.js";

/** Einschätzung des lernenden Modells für einen Wert, mit Begründung und wie sie mit den Regeln kombiniert wird. */
export function ModelCard({ model }) {
  if (!model) {
    return (
      <section className="panel" id="modell">
        <div className="panel-head"><h2><Icon name="brain" className="h-icon" /> Modell</h2><Link className="link small" to="/modell">So lernt es</Link></div>
        <p className="muted small" style={{ margin: 0 }}>Für diesen Wert gibt es noch keine Vorhersage – sie kommt mit dem nächsten Lernlauf.</p>
      </section>
    );
  }
  const w = model.weight || 0;
  const fin = model.final || {};
  return (
    <section className="panel" id="modell">
      <div className="panel-head">
        <h2><Icon name="brain" className="h-icon" /> Modell</h2>
        <span className={`model-chip ${ACTION_UI[model.action]?.tone || ""}`}>{ACTION_UI[model.action]?.label}</span>
      </div>
      <p className="small" style={{ marginTop: 0 }}>In den nächsten {model.days} Handelstagen:</p>
      <ProbBar p={model} />
      {model.drivers?.length > 0 && (
        <>
          <p className="muted small" style={{ margin: "0.9rem 0 0.35rem" }}>Was die Einschätzung treibt (← fallen · steigen →)</p>
          <ul className="drivers">
            {model.drivers.map((d) => <li key={d.group}><span>{d.text}</span><DriverBar delta={d.delta} /></li>)}
          </ul>
        </>
      )}
      <p className="muted small" style={{ margin: "0.9rem 0 0" }}>
        {w > 0
          ? <>Zählt zu {Math.round(w * 100)} % neben den Regeln ({ACTION_UI[model.rule?.action]?.short}) → zusammen: <strong>{ACTION_UI[fin.action]?.label}</strong>. Käufe brauchen immer auch die Regeln.</>
          : <>Das Modell war auf ungesehenen Daten zuletzt nicht besser als der Zufall – es wird angezeigt, zählt aber nicht.</>}
      </p>
    </section>
  );
}

/** Was im Netz über den Wert gesagt wird. */
export function SocialCard({ symbol }) {
  const q = useCachedGet(`/social/${encodeURIComponent(symbol)}`, { pollWhile: (d) => d?.refreshing && !d?.data, every: 4000, maxPolls: 6 });
  const s = q.data?.data;
  if (q.data && !q.data.enabled) return null;
  return (
    <section className="panel" id="stimmung">
      <div className="panel-head">
        <h2><Icon name="message" className="h-icon" /> Stimmung im Netz</h2>
        {s?.fetched && <span className="muted small">{ago(new Date(s.fetched * 1000).toISOString())}</span>}
      </div>
      {!s ? <p className="muted small" style={{ margin: 0 }}>{q.data?.refreshing ? "Sammle Beiträge aus StockTwits, Bluesky, Reddit und Wikipedia …" : "Noch keine Daten."}</p> : (
        <>
          <div className="kpi-row" style={{ gap: "1rem 2rem" }}>
            <div><span className="kpi-label">Stimmung</span><span className={`kpi-small ${s.score > 0.15 ? "pos" : s.score < -0.15 ? "neg" : ""}`}>
              {s.score == null ? "–" : s.score > 0.15 ? "positiv" : s.score < -0.15 ? "negativ" : "neutral"}</span></div>
            <div><span className="kpi-label">Beiträge</span><span className="kpi-small">{s.n || 0}</span></div>
            {s.bull_ratio != null && <div><span className="kpi-label">bullish</span><span className="kpi-small">{Math.round(s.bull_ratio * 100)} %</span></div>}
            {s.buzz != null && <div><span className="kpi-label">Buzz (24 h vs. Woche)</span><span className="kpi-small">{num(s.buzz, 1)}×</span></div>}
            {s.attention && <div><span className="kpi-label">Wikipedia-Aufrufe</span><span className="kpi-small">{num(s.attention.ratio, 1)}×</span></div>}
          </div>
          {s.samples?.length > 0 && (
            <ul className="posts" style={{ marginTop: "0.9rem" }}>
              {s.samples.slice(0, 6).map((p) => (
                <li key={p.url || p.text} className={p.sentiment > 0.15 ? "p" : p.sentiment < -0.15 ? "n" : ""}>
                  {p.url ? <a href={p.url} target="_blank" rel="noreferrer noopener">{p.text}</a> : p.text}
                  <div className="src">{p.source}{p.time ? ` · ${ago(p.time)}` : ""}</div>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small" style={{ margin: "0.75rem 0 0" }}>Quellen: {Object.keys(s.sources || {}).filter((k) => !s.sources[k].error).join(", ") || "–"}{s.attention ? ", Wikipedia" : ""}</p>
        </>
      )}
    </section>
  );
}

/* ---------- Warum läuft der Wert so? ---------- */
const sgn = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${num(Math.abs(v), d)} %`);
const tone2 = (v) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

/** Ein Balken je Treiber, Null in der Mitte (links fallen, rechts steigen). */
function PartBar({ value, max }) {
  const w = max ? Math.min(50, (Math.abs(value || 0) / max) * 50) : 0;
  return (
    <span className="why-bar" aria-hidden="true">
      <span className={`why-fill ${value >= 0 ? "up" : "down"}`} style={{ width: `${w}%`, [value >= 0 ? "left" : "right"]: "50%" }} />
    </span>
  );
}

export function WhyCard({ symbol }) {
  const q = useCachedGet(`/why/${encodeURIComponent(symbol)}`, { pollWhile: (d) => d?.pending || d?.refreshing, every: 2500, maxPolls: 20 });
  const d = q.data;
  const windows = d?.windows || [];
  const [sel, setSel] = useStateSafe("Monat");
  const w = windows.find((x) => x.label === sel) || windows[1] || windows[0];
  const parts = w ? [
    { key: "market", label: `Markt (${d.market?.label})`, value: w.market, ref: w.market_ret },
    ...(d.sector ? [{ key: "sector", label: `Branche (${d.sector.label})`, value: w.sector, ref: w.sector_ret }] : []),
    { key: "own", label: "Unternehmen selbst", value: w.own },
  ].filter((p) => p.value != null) : [];
  const max = Math.max(...parts.map((p) => Math.abs(p.value)), Math.abs(w?.total || 0), 1);
  return (
    <section className="panel why" id="warum">
      <div className="panel-head">
        <h2><Icon name="info" className="h-icon" /> Warum läuft der Kurs so?</h2>
      </div>
      {!d || d.pending ? <p className="muted small" style={{ margin: 0 }}>Vergleiche mit Markt und Branche und suche die Nachrichten der stärksten Tage …</p>
        : d.empty || d.error ? <p className="muted small" style={{ margin: 0 }}>{d.reason || "Gerade keine Erklärung möglich."}</p>
        : (
          <>
            <div className="why-summary">{(d.summary || []).slice(0, 2).map((t) => <p key={t}>{t}</p>)}</div>
            {windows.length > 0 && (
              <>
                <div className="seg why-seg" role="group" aria-label="Zeitraum">
                  {windows.map((x) => <button key={x.label} className={x.label === w?.label ? "on" : ""} onClick={() => setSel(x.label)}>{x.label}</button>)}
                </div>
                <div className="why-total">
                  <span>Kurs</span><strong className={tone2(w.total)}>{sgn(w.total)}</strong>
                </div>
                <ul className="why-parts">
                  {parts.map((p) => (
                    <li key={p.key}>
                      <span className="why-label">{p.label}{p.ref != null && <span className="muted small"> · Index {sgn(p.ref)}</span>}</span>
                      <PartBar value={p.value} max={max} />
                      <strong className={tone2(p.value)}>{sgn(p.value)}</strong>
                    </li>
                  ))}
                </ul>
                <p className="muted small why-note">
                  Anteil an der Kursänderung. „Markt“ und „Branche“: so viel hätte der Wert allein durch sie bewegt –
                  geschätzt aus einem Jahr Tageskursen (schwingt {num(d.fit?.beta_m ?? 0, 1)}-fach mit dem {d.market?.label}).
                  {d.sector && " Branche gemessen am US-Branchenindex."}
                </p>
              </>
            )}
            {d.big_days?.length > 0 && (
              <>
                <h3 className="why-h3">Die stärksten Tage (3 Monate)</h3>
                <ul className="why-days">
                  {d.big_days.map((b) => (
                    <li key={b.day}>
                      <div className="why-day-head">
                        <span>{new Date(b.day).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })}</span>
                        <strong className={tone2(b.pct)}>{sgn(b.pct)}</strong>
                        <span className="muted small">Markt {sgn(b.market_pct)}</span>
                      </div>
                      {b.news?.length ? (
                        <ul className="why-news">
                          {b.news.slice(0, 2).map((n) => (
                            <li key={n.url || n.headline}>
                              {n.url ? <a href={n.url} target="_blank" rel="noreferrer noopener">{n.headline}</a> : n.headline}
                              {n.source && <span className="muted small"> · {n.source}</span>}
                            </li>
                          ))}
                        </ul>
                      ) : <p className="muted small" style={{ margin: "0.2rem 0 0" }}>Keine Schlagzeile zu diesem Tag gefunden.</p>}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {(d.summary || []).slice(2).filter((t) => !t.startsWith("Zuletzt deutlich")).map((t) => <p key={t} className="muted small why-more">{t}</p>)}
          </>
        )}
    </section>
  );
}
